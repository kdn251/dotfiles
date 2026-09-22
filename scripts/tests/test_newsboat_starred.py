from contextlib import closing
import copy
import importlib.util
from pathlib import Path
import sqlite3
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
                self.assertIn(server.rows[1]['url'],starred.STARRED_STATUS.read_text())
                self.assertEqual(server.rows[1]['status'],'unread')
                self.assertIn('⭐ Starred',starred.URLS.read_text())
                self.assertNotIn('Shelf',starred.URLS.read_text())
                server.rows[1]['status']='read'
                self.assertEqual(len(starred.entries(server)),1)
                starred.set_star(server.rows[1]['url'],False,server)
                self.assertFalse(server.rows[1]['starred'])
                self.assertEqual(starred.STARRED_STATUS.read_text(),'')
                self.assertEqual(server.rows[1]['status'],'read')
                with patch.object(server,'starred',side_effect=OSError):
                    with self.assertRaises(OSError):starred.set_star(server.rows[1]['url'],True,server)
                self.assertFalse(server.rows[1]['starred'])

    def test_view_shows_read_items_and_never_consumes_them(self):
        with tempfile.TemporaryDirectory() as d:
            server=Server();server.rows[1].update(starred=True,status='read')
            _,config=starred.prepare_view(d,server.starred())
            text=config.read_text()
            self.assertIn('show-read-articles yes',text)
            self.assertNotIn('consume',text)
            self.assertIn('Unstar all displayed items (asks for confirmation)',text)
            self.assertIn('⭐ Starred',(Path(d)/'history.xml').read_text())
