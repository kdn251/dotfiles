from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
spec = importlib.util.spec_from_file_location('shelf', SCRIPTS/'newsboat-shelf.py')
shelf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shelf)


class ShelfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.multiple(shelf, STATE=self.root/'state', CACHE=self.root/'main.db', URLS=self.root/'urls')
        self.patch.start()
        with closing(sqlite3.connect(shelf.CACHE)) as db:
            db.executescript('CREATE TABLE rss_item(url TEXT,title TEXT,content TEXT,feedurl TEXT,pubDate INTEGER,unread INTEGER); CREATE TABLE rss_feed(rssurl TEXT,title TEXT);')
            db.execute('INSERT INTO rss_feed VALUES (?,?)', ('feed','Creator'))
            db.execute('INSERT INTO rss_item VALUES (?,?,?,?,?,1)', ('https://example.com/one','Title','<p>Full article</p>','feed',1))
            db.commit()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_save_is_deduplicated_preserves_content_and_unread(self):
        shelf.save('https://example.com/one');shelf.save('https://example.com/one')
        rows = shelf.entries()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][1:4], ('Title','Creator','<p>Full article</p>'))
        with closing(sqlite3.connect(shelf.CACHE)) as db:
            self.assertEqual(db.execute('SELECT unread FROM rss_item').fetchone()[0],1)

    def test_manual_remove_leaves_original_article_unread(self):
        shelf.save('https://example.com/one')
        shelf.consume('https://example.com/one')
        self.assertEqual(shelf.entries(), [])
        with closing(sqlite3.connect(shelf.CACHE)) as db:
            self.assertEqual(db.execute('SELECT unread FROM rss_item').fetchall(), [(1,)])

    def test_consumed_removed_but_failed_unread_kept(self):
        shelf.save('https://example.com/one');shelf.save('https://example.com/two')
        view = self.root/'view.db'
        with closing(sqlite3.connect(view)) as db:
            db.execute('CREATE TABLE rss_item(url TEXT,unread INTEGER,deleted INTEGER)')
            db.executemany('INSERT INTO rss_item VALUES (?,?,0)', [('https://example.com/one',0),('https://example.com/two',1)])
            db.commit()
        shelf.sync_consumed(view,shelf.time.time())
        self.assertEqual([row[0] for row in shelf.entries()],['https://example.com/two'])


if __name__ == '__main__':unittest.main()
