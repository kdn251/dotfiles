import json
from pathlib import Path
import tempfile
import unittest
from test_newsboat_reconnect import reader

class EmptyNewTests(unittest.TestCase):
    def test_mailbox_changes_when_last_item_read_and_unread(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description><item><title>Article</title><link>https://example.org/a</link><guid>1</guid></item></channel></rss>')
            urls=json.dumps('query:📬 New:unread = "yes"',ensure_ascii=False)+'\n'+feed.as_uri()+'\n'
            cfg='show-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nfeedlist-format "%v %t"\nbind n articlelist toggle-article-read "read" "stay"\nbind u feedlist undo-action\n'
            with reader(root,cfg,urls) as (_,screen,send,wait):
                wait(lambda s:'1 📬 New' in s)
                send('\n');wait(lambda s:'Article' in s)
                send('n');wait(lambda s:'📪 New' in screen.display[0])
                send('q');wait(lambda s:'0 📪 New' in s)
                send('u');wait(lambda s:'1 📬 New' in s)

    def test_glimmer_changes_only_mailbox_pixels_and_keeps_placement(self):
        import io,struct
        from unittest.mock import patch
        from PIL import Image
        from newsboat_playlist_avatars import Avatars,mailbox_png,glimmer_mailbox
        size=struct.pack('HHHH',24,120,1200,480)
        normal=Image.open(io.BytesIO(glimmer_mailbox(size,40)))
        bright=Image.open(io.BytesIO(glimmer_mailbox(size,6)))
        self.assertEqual(normal.getchannel('A').tobytes(),bright.getchannel('A').tobytes())
        self.assertNotEqual(normal.tobytes(),bright.tobytes())
        avatars=Avatars(100)
        ident='newsboat-mailbox://unread'
        avatars.rows=[(22,1,ident)];avatars.images[ident]=mailbox_png()
        with patch('newsboat_playlist_avatars.time.monotonic',return_value=3.2):avatars.render(size)
        with patch('newsboat_playlist_avatars.time.monotonic',return_value=.48):output=avatars.render(size)
        self.assertIn(b'a=t,f=100,i=100',output)
        self.assertNotIn(b'a=d,',output)
        self.assertIn(b'c=2,r=1',output)
        avatars.rows=[]
        self.assertIn(b'a=d,d=I,i=100',avatars.render(size))
