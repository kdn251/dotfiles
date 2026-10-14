"""Opening read and empty feeds from All must not strand the user."""
import json
from pathlib import Path
import tempfile
import unittest
from test_newsboat_reconnect import reader, pyte, BINARY

@unittest.skipUnless(pyte and BINARY.exists(), 'requires native Newsboat and pyte')
class ReadFeedTests(unittest.TestCase):
    def test_all_opens_read_feed_and_toggle_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Example source</title><link>https://example.com</link><description>test</description><item><title>Previously read episode</title><guid>episode</guid><link>https://example.com/episode</link></item></channel></rss>')
            urls=json.dumps('query:🌎 All:unread = "yes"',ensure_ascii=False)+'\n'+feed.as_uri()+'\n'
            cfg='show-read-feeds yes\nshow-read-articles no\nconfirm-exit no\nfeedlist-format "%t %u"\narticlelist-title-format "EPISODES"\nbind c feedlist mark-feed-read\nbind l articlelist toggle-show-read-feeds\nrun-on-startup set-filter '+json.dumps('rssurl =~ "^query:"')+'\n'
            with reader(root,cfg,urls) as (_,screen,send,wait):
                wait(lambda s:'🌎 All' in s);send('\n');wait(lambda s:'Example source' in s)
                send('c');wait(lambda s:'mark this feed as read' in s);send('y');wait(lambda s:'(0/1)' in s)
                send('\n');wait(lambda s:'EPISODES' in s and 'Previously read episode' in s)
                send('l');wait(lambda s:'Previously read episode' not in s)
                send('l');wait(lambda s:'Previously read episode' in s)

    def test_empty_feed_opens(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Empty source</title><link>https://example.com</link><description>test</description></channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles no\nconfirm-exit no\narticlelist-title-format "EMPTY FEED OPEN"\n'
            with reader(root,cfg,feed.as_uri()+'\n') as (_,screen,send,wait):
                wait(lambda s:'Empty source' in s);send('\n');wait(lambda s:'EMPTY FEED OPEN' in s)
                send('q');wait(lambda s:'Empty source' in s)
