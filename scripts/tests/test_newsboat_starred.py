from contextlib import closing
import copy
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('starred',SCRIPTS/'newsboat-starred.py')
starred=importlib.util.module_from_spec(spec);spec.loader.exec_module(starred)

class Server:
    def __init__(self):
        self.rows={1:dict(id=1,url='https://example.com/one',title='One',feed={'title':'Source'},content='Body',starred=False,status='unread')}
    def starred(self):return copy.deepcopy([r for r in self.rows.values() if r['starred']])
    def request(self,path,data=None,method=None):
        if path=='entries':
            for i in data['entry_ids']:self.rows[i]['starred']=data['starred']
        else:return copy.deepcopy(self.rows[int(path.split('/')[-1])])

class StarredTests(unittest.TestCase):
    def test_view_retains_distinct_publication_dates_across_reopens(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Server().rows[1]
            rows = [dict(base, id=1, published_at='2026-08-10T14:30:00-04:00'),
                    dict(base, id=2, published_at='2026-09-21T09:15:00Z'),
                    dict(base, id=3, published_at='invalid', created_at='2026-07-01T12:00:00Z')]
            def dates():
                starred.write_feed(directory, rows)
                return [parsedate_to_datetime(item.findtext('pubDate')).isoformat()
                        for item in ET.parse(Path(directory)/'history.xml').findall('./channel/item')]
            expected = ['2026-08-10T18:30:00+00:00', '2026-09-21T09:15:00+00:00', '2026-07-01T12:00:00+00:00']
            self.assertEqual(dates(), expected)
            with patch.object(starred.time, 'time', return_value=2000000000):
                self.assertEqual(dates(), expected)

    def test_native_starred_view_displays_newest_publication_first(self):
        import os, pty, select, signal, time
        try:
            import pyte
        except ImportError:
            self.skipTest('requires pyte')
        binary = Path.home()/'.local/lib/newsboat-paged/newsboat'
        if not binary.exists():
            self.skipTest('requires native Newsboat')
        with tempfile.TemporaryDirectory() as directory:
            base = Server().rows[1]
            rows = [dict(base, id=1, title='OldestArticle', published_at='2026-07-01T12:00:00Z'),
                    dict(base, id=2, title='NewestArticle', published_at='2026-09-23T12:00:00Z'),
                    dict(base, id=3, title='MiddleArticle', published_at='2026-08-01T12:00:00Z')]
            command, config = starred.prepare_view(directory, rows)
            command[0] = str(binary)
            subprocess.run(command+['-x','reload'],check=True,capture_output=True)
            with config.open('a') as output:
                output.write('run-on-startup open\n')
            pid, fd = pty.fork()
            if pid == 0:
                os.environ['TERM'] = 'xterm-256color'
                os.execv(str(binary), command)
            screen = pyte.Screen(100,24)
            stream = pyte.ByteStream(screen)
            try:
                end = time.monotonic()+5
                while time.monotonic()<end:
                    if select.select([fd],[],[],.05)[0]:
                        stream.feed(os.read(fd,65536))
                    text = '\n'.join(screen.display)
                    if all(title in text for title in ['OldestArticle','NewestArticle','MiddleArticle']):
                        break
                self.assertLess(text.index('NewestArticle'),text.index('MiddleArticle'))
                self.assertLess(text.index('MiddleArticle'),text.index('OldestArticle'))
            finally:
                os.kill(pid,signal.SIGTERM)
                os.waitpid(pid,0)
                os.close(fd)

    def test_direct_idempotent_stars_leave_read_status_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);server=Server()
            with patch.multiple(starred,CACHE=root/'cache',URLS=root/'urls',STARRED_STATUS=root/'starred-status'):
                with closing(sqlite3.connect(starred.CACHE)) as db,db:
                    db.execute('CREATE TABLE rss_item(guid TEXT,url TEXT)')
                    db.execute('INSERT INTO rss_item VALUES (?,?)',('1',server.rows[1]['url']))
                starred.URLS.write_text('"query:📚 Shelf:link = \\"none\\""\n')
                for _ in range(2):starred.set_star(server.rows[1]['url'],True,server)
                self.assertTrue(server.rows[1]['starred'])
                self.assertEqual(Path(str(starred.STARRED_STATUS)+'.count').read_text(), '1\n')
                self.assertIn(server.rows[1]['url'],starred.STARRED_STATUS.read_text())
                self.assertEqual(server.rows[1]['status'],'unread')
                self.assertIn('⭐ Starred',starred.URLS.read_text())
                self.assertNotIn('Shelf',starred.URLS.read_text())
                server.rows[1]['status']='read'
                self.assertEqual(len(starred.entries(server)),1)
                starred.set_star(server.rows[1]['url'],False,server)
                self.assertFalse(server.rows[1]['starred'])
                self.assertEqual(starred.STARRED_STATUS.read_text(),'')
                self.assertEqual(Path(str(starred.STARRED_STATUS)+'.count').read_text(), '0\n')
                self.assertEqual(server.rows[1]['status'],'read')
                with patch.object(server,'starred',side_effect=OSError):
                    with self.assertRaises(OSError):starred.set_star(server.rows[1]['url'],True,server)
                self.assertFalse(server.rows[1]['starred'])

    def test_view_shows_read_items_and_never_consumes_them(self):
        with tempfile.TemporaryDirectory() as d:
            server=Server();server.rows[1].update(starred=True,status='read')
            command,config=starred.prepare_view(d,server.starred())
            text=config.read_text()
            self.assertIn('show-read-articles yes',text)
            self.assertNotIn('consume',text)
            self.assertIn('Unstar all displayed items (asks for confirmation)',text)
            self.assertIn('⭐ Starred',(Path(d)/'history.xml').read_text())
            binary = Path.home()/'.local/lib/newsboat-paged/newsboat'
            if binary.exists():
                command[0] = str(binary)
                result = subprocess.run(command+['-x','reload'], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_generated_view_preserves_server_read_and_unread_states(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with closing(sqlite3.connect(root/'cache.db')) as db, db:
                db.execute('CREATE TABLE rss_item(guid TEXT, unread INTEGER)')
                db.executemany('INSERT INTO rss_item VALUES (?, 1)', [('1',), ('2',)])
            starred.sync_read_status(root, [dict(id=1, status='read'), dict(id=2, status='unread')])
            with closing(sqlite3.connect(root/'cache.db')) as db:
                self.assertEqual(db.execute('SELECT guid, unread FROM rss_item ORDER BY guid').fetchall(),
                                 [('1', 0), ('2', 1)])

    def test_open_uses_synced_snapshot_without_network_and_keeps_local_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rows=[dict(id=1,url='https://example.com/one',status='unread')]
            with patch.multiple(starred, CACHE=root/'cache', URLS=root/'urls', STARRED_STATUS=root/'stars'):
                with closing(sqlite3.connect(starred.CACHE)) as db, db:
                    db.execute('CREATE TABLE rss_item(guid TEXT, unread INTEGER)')
                    db.execute("INSERT INTO rss_item VALUES ('1', 0)")
                starred.rebuild_query(rows)
                with patch.object(starred, 'entries', side_effect=AssertionError('Network on open')):
                    self.assertEqual(starred.view_entries()[0]['status'], 'read')
                starred.rebuild_query([])
                with patch.object(starred, 'entries', side_effect=AssertionError('Network on open')):
                    self.assertEqual(starred.view_entries(), [])
