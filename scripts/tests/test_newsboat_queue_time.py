import json
import sqlite3
import unittest
from unittest.mock import patch
import newsboat_queue_time as timing
import newsboat_queue as queue
import newsboat_watch_progress as progress
from test_newsboat_queue import isolated,URLS
from test_newsboat_reconnect import reader

class QueueTimeTests(unittest.TestCase):
    def test_remaining_and_partial_unknown_and_completion(self):
        with isolated() as (root,_):
            for url in URLS[:2]:queue.change('add',url)
            with patch.object(progress,'STATE',queue.state()):
                progress.record(URLS[0],600,1800)
                self.assertEqual((queue.state()/'viewing-queue.tsv.time').read_text().strip(),'about 20 min remaining · 1 unknown')
                progress.record(URLS[1],180,900)
                self.assertAlmostEqual(timing.remaining(queue.entries())[0],1920)
                self.assertEqual(timing.remaining(queue.entries())[1],[])
                self.assertEqual((queue.state()/'viewing-queue.tsv.time').read_text().strip(),'about 32 min remaining')
                progress.record(URLS[0],1800,1800)
                progress.record(URLS[1],900,900)
                self.assertEqual(timing.remaining(queue.entries()),(0,[]))
                self.assertEqual(timing.label(0,0,2),'0 min remaining')

    def test_background_resolver_caches_and_retries_failures_later(self):
        with isolated():
            for url in URLS[:2]:queue.change('add',url)
            with patch.object(timing,'resolve_duration',side_effect=[3600,0]) as resolve:
                timing.resolve()
                self.assertEqual(resolve.call_count,2)
                timing.resolve()
                self.assertEqual(resolve.call_count,2,'failed lookup is not retried in a tight loop')
            self.assertEqual(timing.remaining(queue.entries()),(3600,[URLS[1]]))
            self.assertEqual((queue.state()/'viewing-queue.tsv.time').read_text().strip(),'about 1h remaining · 1 unknown')

    def test_homepage_updates_time_while_watching(self):
        with isolated() as (root,urls):
            queue.change('add',URLS[0])
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],0,1800)
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>test</description></channel></rss>')
            cfg='show-read-feeds yes\nconfirm-exit no\nprepopulate-query-feeds yes\nfeedlist-format "%v %k %t"\n'
            env=dict(NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_STARRED_STATUS=str(queue.state()/'starred-urls.txt'))
            with reader(root,cfg,urls.read_text()+feed.as_uri()+'\n',env) as (_,screen,send,wait):
                wait(lambda s:'1 video 📺 Queue · about 30 min remaining' in s)
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],900,1800)
                wait(lambda s:'1 video 📺 Queue · about 15 min remaining' in s)
