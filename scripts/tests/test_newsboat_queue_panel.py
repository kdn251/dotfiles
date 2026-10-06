import unittest
from unittest.mock import patch
import newsboat_queue_panel as panel
import newsboat_queue as queue
import newsboat_watch_progress as progress
from test_newsboat_queue import isolated, URLS
from test_newsboat_reconnect import reader

class QueueHeaderTests(unittest.TestCase):
    def test_live_progress_order_and_empty_queue(self):
        with isolated():
            for url in URLS[:2]:queue.change('add',url)
            with patch.object(progress,'STATE',queue.state()):
                progress.record(URLS[0],120,600)
                progress.record(URLS[1],60,1200)
            header=panel.Header();header.update()
            self.assertIn('Video0\tCreator\t━━────── 20% · 8:00 left',header.path.read_text())
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],300,600)
            header.due=0;header.update()
            self.assertIn('50% · 5:00 left',header.path.read_text())
            queue.change('move-before',URLS[1],URLS[0]);header.due=0;header.update()
            self.assertTrue(header.path.read_text().startswith('Video1\t'))
            for url in URLS[:2]:queue.change('remove',url)
            header.due=0;header.update()
            self.assertEqual(header.path.read_text(),'')

    def test_native_title_row_on_home_list_and_help(self):
        with isolated() as (root,_):
            queue.change('add',URLS[0])
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],120,600)
            header=panel.Header();header.update()
            feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>test</description><item><guid>1</guid><title>Article</title><link>https://example.org/1</link></item></channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nfeedlist-title-format " Newsboat"\narticlelist-title-format " Source"\n'
            with reader(root,cfg,feed.as_uri()+'\n',{'NEWSBOAT_QUEUE_HEADER':str(header.path)}) as (_,screen,send,wait):
                wait(lambda _: 'Newsboat' in screen.display[0] and 'Video0' in screen.display[0])
                self.assertTrue(screen.display[0].endswith('8:00 left '))
                send('\n');wait(lambda _: 'Source' in screen.display[0] and 'Creator' in screen.display[0])
                send('?');wait(lambda _: 'Help' in screen.display[0] and '20%' in screen.display[0])
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],300,600)
                header.due=0;header.update()
                wait(lambda _: '50%' in screen.display[0])
                queue.change('remove',URLS[0]);header.due=0;header.update()
                wait(lambda _: 'Video0' not in screen.display[0])
