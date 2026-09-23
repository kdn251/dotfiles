from contextlib import closing
import copy
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
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
