from contextlib import closing
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
spec = importlib.util.spec_from_file_location('history', SCRIPTS/'newsboat-history.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patch = patch.multiple(history, STATE=root/'state', CACHE=root/'cache.db')
        self.patch.start()
        with closing(sqlite3.connect(history.CACHE)) as db:
            db.executescript('CREATE TABLE rss_feed(rssurl TEXT,title TEXT); CREATE TABLE rss_item(url TEXT,title TEXT,feedurl TEXT,pubDate INTEGER);')
            db.execute('INSERT INTO rss_feed VALUES (?,?)', ('feed', 'A source'))
            db.execute('INSERT INTO rss_item VALUES (?,?,?,?)', ('https://example.com/1', 'A title with "quotes"', 'feed', 1))
            db.commit()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_titles_order_and_reopening_moves_to_top(self):
        history.record('https://example.com/1', 'browser')
        history.record('https://example.com/2', 'video')
        history.record('https://example.com/1', 'video')
        rows = history.entries()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][:4], ('https://example.com/1', 'A title with "quotes"', 'A source', 'video'))
        self.assertEqual((history.STATE/'history.db').stat().st_mode & 0o777, 0o600)

    def test_missing_cache_and_bounded_history(self):
        history.CACHE.unlink()
        for i in range(502):
            history.record(f'https://example.com/{i}', 'browser')
        self.assertEqual(len(history.entries()), 500)
        history.record('file:///private', 'browser')
        self.assertEqual(len(history.entries()), 500)

    def test_native_feed_preserves_urls_titles_and_open_times(self):
        import xml.etree.ElementTree as ET
        history.record('https://example.com/1', 'browser')
        history.record('https://example.com/2', 'video')
        directory = Path(self.temp.name)
        command, config = history.prepare_view(directory)
        items = ET.parse(directory/'history.xml').findall('./channel/item')
        self.assertEqual([item.findtext('link') for item in items],
                         ['https://example.com/2', 'https://example.com/1'])
        self.assertIn('A title with "quotes"', items[1].findtext('title'))
        self.assertIn('bind q articlelist hard-quit', config.read_text())
        self.assertNotIn('miniflux', config.read_text())
        self.assertEqual(command[0], 'newsboat')


if __name__ == '__main__':
    unittest.main()
