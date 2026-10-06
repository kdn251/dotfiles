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
                self.assertEqual((queue.state()/'viewing-queue.tsv.time').read_text().strip(),'~20 mins · 1 unknown')
                progress.record(URLS[1],180,900)
                self.assertAlmostEqual(timing.remaining(queue.entries())[0],1920)
                self.assertEqual(timing.remaining(queue.entries())[1],[])
                self.assertEqual((queue.state()/'viewing-queue.tsv.time').read_text().strip(),'~32 mins')
                progress.record(URLS[0],1800,1800)
                progress.record(URLS[1],900,900)
                self.assertEqual(timing.remaining(queue.entries()),(0,[]))
                self.assertEqual(timing.label(0,0,2),'~0 min')

    def test_background_resolver_caches_and_retries_failures_later(self):
        with isolated():
            for url in URLS[:2]:queue.change('add',url)
            with patch.object(timing,'resolve_duration',side_effect=[3600,0]) as resolve:
                timing.resolve()
                self.assertEqual(resolve.call_count,2)
                timing.resolve()
                self.assertEqual(resolve.call_count,2,'failed lookup is not retried in a tight loop')
            self.assertEqual(timing.remaining(queue.entries()),(3600,[URLS[1]]))
            self.assertEqual((queue.state()/'viewing-queue.tsv.time').read_text().strip(),'~1h · 1 unknown')

    def test_homepage_updates_time_while_watching(self):
        with isolated() as (root,urls):
            queue.change('add',URLS[0])
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],0,1800)
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>test</description></channel></rss>')
            cfg='show-read-feeds yes\nconfirm-exit no\nprepopulate-query-feeds yes\nfeedlist-format " %3i  %n %S  %4v %-6k  %t"\n'
            env=dict(NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_STARRED_STATUS=str(queue.state()/'starred-urls.txt'))
            with reader(root,cfg,urls.read_text()+feed.as_uri()+'\n',env) as (_,screen,send,wait):
                wait(lambda s:'~30 mins 📺 Queue' in ' '.join(s.split()))
                self.assertNotIn('video',next(row for row in screen.display if '📺 Queue' in row))
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],900,1800)
                wait(lambda s:'~15 mins 📺 Queue' in ' '.join(s.split()))
                queue.change('add',URLS[1])
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[1],0,1200)
                wait(lambda s:'~35 mins 📺 Queue' in ' '.join(s.split()))

    def test_queue_title_updates_time_and_membership(self):
        with isolated() as (root,_):
            for url in URLS[:2]:queue.change('add',url)
            with patch.object(progress,'STATE',queue.state()):
                progress.record(URLS[0],0,1800)
                progress.record(URLS[1],0,1200)
            view=root/'view';view.mkdir();queue.prepare_view(view)
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticlelist-title-format " 📺 Queue"\narticlelist-format "%4i %4w %t"\nrun-on-startup open\n'
            env=dict(NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_QUEUE_VIEW='1',NEWSBOAT_DOWNLOAD_STATUS=str(queue.state()/'download-status.tsv'))
            with reader(view,cfg,(view/'history.xml').as_uri()+'\n',env) as (_,screen,send,wait):
                wait(lambda _: '📺 Queue (~50 mins)' in screen.display[0])
                self.assertNotIn('video',screen.display[0])
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],900,1800)
                wait(lambda _: '~35 mins' in screen.display[0])
                wait(lambda _:any('Video0' in row and '50%' in row for row in screen.display[1:-3]))
                # Pausing/elapsed wall time cannot consume unwatched content.
                summary=queue.state()/'viewing-queue.tsv.time'
                timestamp=summary.stat().st_mtime_ns
                with patch('newsboat_queue_time.time.time',return_value=9999999999):timing.refresh()
                self.assertEqual(summary.stat().st_mtime_ns,timestamp)
                # Seeking backwards increases the estimate; seeking forwards reduces it.
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],300,1800)
                wait(lambda _: '~45 mins' in screen.display[0])
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],900,1800)
                wait(lambda _: '~35 mins' in screen.display[0])
                queue.change('finished',URLS[1],queue.entries()[1]['queue_token'])
                wait(lambda _: '📺 Queue (~15 mins)' in screen.display[0])
                with patch.dict('os.environ',NEWSBOAT_QUEUE_UNDO_TOKEN='title-test'):
                    queue.change('remove',URLS[0])
                wait(lambda _: screen.display[0].strip() == '📺 Queue')
                queue.change('restore',URLS[0],'title-test')
                wait(lambda _: '📺 Queue (~15 mins)' in screen.display[0])
