import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import newsboat_video_dates as dates
from test_newsboat_reconnect import reader,pyte,BINARY
URL='https://www.youtube.com/watch?v=abc123DEF45'

class DateTests(unittest.TestCase):
    def test_publication_date_precedes_private_upload(self):
        self.assertEqual(dates.date_from_page('{"uploadDate":"2026-09-01T12:00:00Z","publishDate":"2026-10-12T10:08:28-07:00"}'),'2026-10-12')
        self.assertEqual(dates.date_from_page('{"uploadDate":"2025-01-02"}'),'2025-01-02')
        self.assertEqual(dates.date_from_page('unavailable'),'')
    def test_dates_when_player_requires_sign_in(self):
        page=json.dumps({'playabilityStatus':{'status':'LOGIN_REQUIRED'},
                         'header':{'publishDate':{'simpleText':'Mar 21, 2020'}},
                         'recommendation':{'publishedTimeText':{'simpleText':'2 days ago'}}})
        self.assertEqual(dates.date_from_page(page),'2020-03-21')
        self.assertEqual(dates.date_from_page('{"publishDate":{"runs":[{"text":"Premiered Aug 26, 2026"}]}}'),'2026-08-26')
        self.assertEqual(dates.date_from_page('{"videoPrimaryInfoRenderer":{"dateText":{"simpleText":"Streamed live on Oct 4, 2026"}}}'),'2026-10-04')
        self.assertEqual(dates.date_from_page('{"recommendation":{"dateText":{"simpleText":"Oct 4, 2026"}}}'),'')

    def test_old_failures_retry_but_successful_dates_survive(self):
        cache={'failed':{'date':'','checked':time.time()},
               'success':{'date':'2020-03-21','checked':0}}
        with tempfile.TemporaryDirectory() as d,patch.object(dates.timing,'state',return_value=Path(d)),patch.object(dates.timing,'read',return_value=cache):
            worker=dates.Dates()
            self.assertNotIn('failed',worker.cache)
            self.assertEqual(worker.cache['success']['date'],'2020-03-21')

    def test_display_matches_other_lists_and_handles_missing_dates(self):
        self.assertEqual(dates.display_date('2026-10-12'),'Oct 12')
        self.assertEqual(dates.display_date('2020-03-01'),'Mar 01')
        self.assertEqual(dates.display_date(''),'—')
        self.assertEqual(dates.display_date(None),'—')

    def test_visible_dates_are_async_and_cached(self):
        with tempfile.TemporaryDirectory() as d,patch.object(dates.timing,'state',return_value=Path(d)):
            p=Path(d)/'youtube-playlists/videos/abc123DEF45.json';p.parent.mkdir(parents=True);p.write_text('{}')
            ready=threading.Event();release=threading.Event()
            def lookup(url):ready.set();release.wait(2);return '2026-10-12'
            with patch.object(dates,'lookup',side_effect=lookup) as lookup_mock:
                worker=dates.Dates();worker.update('10;1;'+URL+'\tCreator\tfeed\n')
                self.assertTrue(ready.wait(1));worker.poll();self.assertEqual(worker.path.read_text(),'')
                release.set();deadline=time.monotonic()+2
                while worker.results.empty() and time.monotonic()<deadline:time.sleep(.01)
                worker.poll();self.assertEqual(worker.path.read_text(),URL+'\tOct 12\n')
                cached=dates.Dates();cached.update('10;1;'+URL);cached.poll()
                self.assertEqual(cached.path.read_text(),URL+'\tOct 12\n');lookup_mock.assert_called_once_with(URL)
    @unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
    def test_native_date_updates_without_moving_cursor(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);status=root/'dates';status.write_text('')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Playlist</title><link>https://youtube.com</link><description>test</description>'+''.join('<item><title>Episode '+str(i)+'</title><guid>'+str(i)+'</guid><link>'+u+'</link></item>' for i,u in enumerate((URL,'https://www.youtube.com/watch?v=abc123DEF46')) )+'</channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-format "%i %10J %t"\nrun-on-startup open\nbind-key j down\n'
            with reader(root,cfg,feed.as_uri()+'\n',{'NEWSBOAT_VIDEO_DATES':str(status)}) as (_,screen,send,wait):
                wait(lambda s:'Episode 0' in s);send('j');wait(lambda _:screen.cursor.y==2)
                status.write_text(URL+'\t2026-10-12\n')
                wait(lambda s:'2026-10-12' in s);self.assertEqual(screen.cursor.y,2)
