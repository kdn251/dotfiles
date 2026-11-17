from contextlib import closing
import json
import sqlite3
import unittest
from unittest.mock import patch
from test_newsboat_queue import isolated,URLS
import newsboat_queue as queue
import newsboat_queue_time as timing

class MixedQueueTimeTests(unittest.TestCase):
    def test_article_and_video_remaining_time_are_combined(self):
        with isolated():
            root=queue.state();root.mkdir(exist_ok=True)
            article='https://example.org/essay'
            rows=[{'url':article},{'url':URLS[0]},{'url':URLS[1]}]
            (root/'video-durations.json').write_text(json.dumps({
                'article:'+article:{'duration':360,'reading_version':2},
                timing.duration_key(URLS[0]):{'duration':600}}))
            timing.publish(rows)
            self.assertEqual((root/'viewing-queue.tsv.time').read_text(),'~16 mins\n')
            with closing(sqlite3.connect(root/'reading-progress.db')) as db:
                db.execute('CREATE TABLE articles (url TEXT, fraction REAL)')
                db.execute('INSERT INTO articles VALUES (?,?)',(article,.5))
                db.commit()
            timing.publish(rows)
            self.assertEqual((root/'viewing-queue.tsv.time').read_text(),'~13 mins\n')

    def test_article_resolution_uses_reading_estimator_not_video_downloader(self):
        with patch('newsboat_reading_time.estimate',return_value=360) as estimate,patch.object(timing.subprocess,'run') as run:
            self.assertEqual(timing.resolve_duration('https://example.org/a'),360)
            estimate.assert_called_once_with('https://example.org/a',allow_fetch=True)
            run.assert_not_called()

    def test_multiple_articles_have_distinct_cache_entries(self):
        with isolated(),patch.object(timing,'resolve_duration',side_effect=[360,240]):
            root=queue.state();root.mkdir(exist_ok=True)
            urls=['https://example.org/a','https://example.org/b']
            (root/'viewing-queue.json').write_text(json.dumps([{'url':u} for u in urls]))
            timing.resolve()
            self.assertEqual((root/'viewing-queue.tsv.time').read_text(),'~10 mins\n')
            self.assertEqual(len(json.loads((root/'queue-durations.json').read_text())),2)

    def test_missing_estimate_never_claims_zero_or_shows_counts(self):
        self.assertEqual(timing.label(0,1,1),'~…')
        self.assertEqual(timing.label(360,1,2),'~6 mins')
