"""Exercise New-list refresh anchoring in a real isolated Newsboat terminal."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from test_newsboat_reconnect import reader, pyte, BINARY


@unittest.skipUnless(pyte and BINARY.exists(), 'requires Newsboat and pyte')
class RefreshAnchorTests(unittest.TestCase):
    def test_near_top(self):
        self.check_refresh(4)

    def test_scrolled_down(self):
        self.check_refresh(20)

    def check_refresh(self, moves):
        chosen=f"Article {39-moves:03}"
        following=f"Article {38-moves:03}"
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);feed=root/'feed.xml'
            def publish(count):
                feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>test</description>'+''.join(
                    f'<item><title>Article {i:03}</title><guid>item-{i}</guid><link>https://example.org/{i}</link><pubDate>Tue, 04 Nov 2025 12:{i:02}:00 GMT</pubDate></item>'
                    for i in range(count))+'</channel></rss>')
            publish(40)
            urls=json.dumps('query:📬 New:unread = "yes"',ensure_ascii=False)+'\n'+feed.as_uri()+'\n'
            config='auto-reload no\nsuppress-first-reload yes\nshow-read-feeds yes\nprepopulate-query-feeds yes\nconfirm-exit no\narticle-sort-order title-desc\narticlelist-format "%i %t"\nscrolloff 100\nbind-key R reload-all\nbind-key j down\nbind-key k up\n'
            with reader(root,config,urls) as (_,screen,send,wait):
                wait(lambda s:'New' in s)
                send('\n');wait(lambda s:'Article 039' in s)
                send('j'*moves);wait(lambda s:chosen in screen.display[screen.cursor.y])
                y=screen.cursor.y
                def selected():return screen.display[screen.cursor.y]
                for count in (43,46):
                    publish(count);send('R')
                    wait(lambda s:f'{count} unread' in s)
                    settled=time.monotonic();wait(lambda s:time.monotonic()-settled>.2)
                    self.assertIn(chosen,selected())
                    self.assertEqual(screen.cursor.y,y)
                    # A later redraw must not recenter the preserved row.
                    send('\x0c');settled=time.monotonic();wait(lambda s:time.monotonic()-settled>.2)
                    self.assertIn(chosen,selected())
                    self.assertEqual(screen.cursor.y,y)
                send('j');wait(lambda s:following in selected())
                send('k');wait(lambda s:chosen in selected())
