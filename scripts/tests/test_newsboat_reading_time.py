import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import newsboat_reading_time as reading
import newsboat_video_duration as durations

URL='https://example.org/essay'

class ReadingTimeTests(unittest.TestCase):
    def test_cached_text_excludes_markup_and_script(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory)/'cache.db'
            with sqlite3.connect(cache) as db:
                db.execute('CREATE TABLE rss_item(url TEXT,content TEXT)')
                db.execute('INSERT INTO rss_item VALUES (?,?)',(URL,'<script>'+('hidden '*1000)+'</script><p>'+('word '*440)+'</p>'))
            with patch.dict('os.environ',NEWSBOAT_CACHE=str(cache)),patch('newsboat_articles.find',return_value=None):
                self.assertEqual(reading.estimate(URL),120)
                self.assertEqual(reading.label(120),'~2m')
                self.assertEqual(reading.label(120,.5),'~1m')
                self.assertEqual(reading.label(120,1),'0m')
            self.assertIsNone(reading.article_key('https://twitch.tv/creator'))
            self.assertIsNone(reading.article_key('newsboat-playthroughs://abc'))

    def test_local_copy_and_live_remaining_estimate(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(reading.timing,'state',return_value=Path(directory)):
            local=Path(directory)/'article.html';local.write_text('<article>'+('word '*660)+'</article>')
            with patch('newsboat_articles.find',return_value=local):self.assertEqual(reading.estimate(URL),180)
            with sqlite3.connect(Path(directory)/'reading-progress.db') as db:
                db.execute('CREATE TABLE articles(url TEXT,fraction REAL)')
                db.execute('INSERT INTO articles VALUES (?,?)',(URL,0))
            worker=durations.Durations();worker.aliases[URL]=reading.article_key(URL)
            worker.results.put((URL,dict(duration=180,checked=time.time(),reading_version=2)))
            worker.poll();self.assertIn('~3m',worker.path.read_text())
            with sqlite3.connect(Path(directory)/'reading-progress.db') as db:db.execute('UPDATE articles SET fraction=.7')
            worker.reading_due=0;worker.poll();self.assertIn('~1m',worker.path.read_text())

    def test_commentary_text_and_remote_fallback(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(reading.timing,'state',return_value=Path(directory)),patch('newsboat_articles.find',return_value=None),patch.dict('os.environ',NEWSBOAT_CACHE=directory+'/absent'):
            with sqlite3.connect(Path(directory)/'commentary.db') as db:
                db.execute('CREATE TABLE items(url TEXT,content TEXT)')
                db.execute('INSERT INTO items VALUES (?,?)',(URL,'<p>'+('word '*440)+'</p>'))
            self.assertEqual(reading.estimate(URL),120)
            with sqlite3.connect(Path(directory)/'commentary.db') as db:db.execute("UPDATE items SET content='short link'")
            from types import SimpleNamespace
            with patch.object(reading.subprocess,'run',return_value=SimpleNamespace(stdout='600')) as fetch:
                self.assertEqual(reading.estimate(URL,allow_fetch=True),600)
                fetch.assert_called_once()
