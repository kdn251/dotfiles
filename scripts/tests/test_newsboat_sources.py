import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import newsboat_sources as sources
import newsboat_offline as offline


class SourceTests(unittest.TestCase):
    def test_offline_uses_saved_names_without_changing_original_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root/'cache.db'
            (root/'feed-titles.json').write_text(json.dumps({'42': 'Channel Name'}))
            with sqlite3.connect(cache) as db:
                db.execute('CREATE TABLE rss_feed(rssurl TEXT,title TEXT)')
                db.execute('CREATE TABLE rss_item(url TEXT,feedurl TEXT)')
                db.execute("INSERT INTO rss_feed VALUES ('42','')")
                db.execute("INSERT INTO rss_item VALUES ('https://youtu.be/example','42')")
            self.assertEqual(sources.article_sources(cache, root)['https://youtu.be/example'], 'Channel Name')
            config=root/'config';config.write_text('')
            urls=root/'urls';urls.write_text('')
            view=root/'offline';view.mkdir()
            with patch.object(offline, 'feed_titles', return_value=sources.feed_titles(root)):
                offline.prepare(view, config, urls, cache)
            with sqlite3.connect(view/'cache.db') as db:
                self.assertEqual(db.execute('SELECT title FROM rss_feed').fetchone()[0], 'Channel Name')
            with sqlite3.connect(cache) as db:
                self.assertEqual(db.execute('SELECT title FROM rss_feed').fetchone()[0], '')
            self.assertEqual(sources.source_label('https://youtu.be/example','Channel Name'), ' Channel Name')
