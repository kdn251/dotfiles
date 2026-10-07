import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import newsboat_video_duration as duration
from test_newsboat_reconnect import reader

URL='https://www.youtube.com/watch?v=abc123DEF45'

class DurationTests(unittest.TestCase):
    def test_background_lookup_cache_and_article_filter(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(duration.timing,'state',return_value=Path(directory)), patch.object(duration,'cached_duration',return_value=0):
            ready=threading.Event();release=threading.Event()
            def resolve(url):
                ready.set();release.wait(2);return 754
            with patch.object(duration.timing,'resolve_duration',side_effect=resolve) as lookup:
                worker=duration.Durations()
                marker='10;1;'+URL+'\tCreator\tfeed\n10;2;https://example.org/article\tAuthor\tfeed\n'
                worker.update(marker)
                self.assertTrue(ready.wait(1))
                worker.poll();self.assertEqual(worker.path.read_text(),'')
                release.set()
                limit=time.monotonic()+2
                while worker.results.empty() and time.monotonic()<limit:time.sleep(.01)
                worker.poll()
                self.assertEqual(worker.path.read_text(),URL+'\t12:34\n')
                cached=duration.Durations();cached.update(marker);cached.poll()
                self.assertEqual(cached.path.read_text(),URL+'\t12:34\n')
                lookup.assert_called_once_with(URL)
                self.assertEqual(duration.label(3735),'1:02:15')
                self.assertEqual(duration.label(0),'—')

    def test_failure_is_cached_without_endless_loading_or_retry(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(duration.timing,'state',return_value=Path(directory)):
            worker=duration.Durations()
            worker.results.put((URL,dict(duration=0,checked=time.time())))
            worker.poll()
            worker.update('10;1;'+URL)
            worker.poll()
            self.assertEqual(worker.path.read_text(),URL+'\t—\n')
            self.assertTrue(worker.jobs.empty())

    def test_native_duration_updates_without_moving_selected_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=root/'durations.tsv';status.write_text('')
            feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Videos</title><link>https://example.org</link><description>Test</description><item><title>Video title</title><guid>1</guid><link>'+URL+'</link></item><item><title>Article title</title><guid>2</guid><link>https://example.org/article</link></item></channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-format "%i %t"\nrun-on-startup open\nbind-key j down\n'
            with reader(root,cfg,feed.as_uri()+'\n',{'NEWSBOAT_VIDEO_DURATIONS':str(status)}) as (_,screen,send,wait):
                wait(lambda s:'Video title' in s and '…' in screen.display[1])
                send('j');wait(lambda _:screen.cursor.y==2)
                status.write_text(URL+'\t12:34\n')
                wait(lambda _: '12:34' in screen.display[1])
                self.assertEqual(screen.cursor.y,2)
                self.assertNotIn('12:34',screen.display[2])
                self.assertNotIn('…',screen.display[2])
