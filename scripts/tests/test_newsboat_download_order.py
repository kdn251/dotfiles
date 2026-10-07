"""Active downloads, watched percentage, then newest downloaded."""
from pathlib import Path
import tempfile
import unittest
from test_newsboat_reconnect import reader

class DownloadOrderTests(unittest.TestCase):
    def test_watched_then_newest_below_stable_active_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description>'+''.join(f'<item><title>Video{i}</title><guid>{i}</guid><link>https://example.org/{i}</link></item>' for i in range(6))+'</channel></rss>')
            status=root/'status'
            status.write_text('https://example.org/0\t↓10%\nhttps://example.org/1\t↓90%\nhttps://example.org/2\t✓\nhttps://example.org/3\t✓\n')
            order=root/'status.order';order.write_text('https://example.org/2\t100\nhttps://example.org/3\t200\nhttps://example.org/4\t400\nhttps://example.org/5\t500\n')
            watched=root/'status.watched';watched.write_text('https://example.org/2\t90%\nhttps://example.org/3\t0%\n')
            urls='"query:📥 Downloads:title =~ \\"Video\\""\n'+feed.as_uri()+'\n'
            cfg='show-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nconfirm-exit no\narticle-sort-order title-asc\narticlelist-format "%i %t"\nrun-on-startup open\n'
            with reader(root,cfg,urls,{'NEWSBOAT_DOWNLOAD_STATUS':str(status)}) as (_,screen,send,wait):
                def titles():return [line.split('Video')[1][0] for line in screen.display[1:-3] if 'Video' in line]
                wait(lambda _:titles()==['0','1','2','5','4','3'])
                watched.write_text('https://example.org/2\t100%\nhttps://example.org/3\t20%\n')
                status.write_text('https://example.org/0\t↓95%\nhttps://example.org/1\t↓20%\nhttps://example.org/2\t✓\nhttps://example.org/3\t✓\n')
                wait(lambda s:'100%' in s and '20%' in s and titles()==['0','1','2','3','5','4'])
                order.write_text('https://example.org/0\t600\nhttps://example.org/2\t100\nhttps://example.org/3\t200\nhttps://example.org/4\t400\nhttps://example.org/5\t500\n')
                status.write_text('https://example.org/0\t✓\nhttps://example.org/1\t↓20%\nhttps://example.org/2\t✓\nhttps://example.org/3\t✓\n')
                wait(lambda _:titles()==['1','2','3','0','5','4'])
