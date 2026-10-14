"""Playthroughs shortcut routes to the library without changing the browser."""
from pathlib import Path
import tempfile
import time
import unittest
from test_newsboat_reconnect import reader,pyte,BINARY

@unittest.skipUnless(pyte and BINARY.exists(), 'requires native Newsboat and pyte')
class ShortcutTests(unittest.TestCase):
    def test_shortcut_from_feed_and_article_lists(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);scripts=root/'scripts';scripts.mkdir();called=root/'called'
            (scripts/'newsboat-playthroughs.py').write_text('from pathlib import Path\np=Path('+repr(str(called))+')\np.write_text(p.read_text()+"open\\n" if p.exists() else "open\\n")\n')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Example feed</title><link>https://example.com</link><description>test</description><item><title>Example video</title><guid>video</guid><link>https://example.com/video</link></item></channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nbind p everywhere set browser "newsboat-playthroughs://show"\n'
            with reader(root,cfg,feed.as_uri()+'\n') as (_,screen,send,wait):
                wait(lambda s:'Example feed' in s);send('p');wait(lambda _:called.exists());time.sleep(.2)
                send('\n');wait(lambda s:'Example video' in s);send('p');wait(lambda _:called.read_text().count('open')==2)
