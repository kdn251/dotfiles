"""Rapid read shortcuts must never turn previously read rows unread."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from test_newsboat_reconnect import reader, pyte, BINARY

CONFIG=Path(__file__).resolve().parents[2]/'newsboat/.newsboat/config'

@unittest.skipUnless(pyte and BINARY.exists(), 'requires native Newsboat and pyte')
class ReadKeyTests(unittest.TestCase):
    def test_rapid_marks_are_idempotent_in_visible_and_unread_lists(self):
        bindings='\n'.join(line for line in CONFIG.read_text().splitlines()
                           if line.startswith(('bind n ', 'bind N ')))
        for show_read in ('yes','no'):
            with self.subTest(show_read=show_read), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);rss=root/'feed.xml'
                rss.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description>'+''.join(f'<item><title>Item {i:02}</title><guid>{i:02}</guid><link>https://example.com/{i}</link></item>' for i in range(12))+'</channel></rss>')
                config=f'show-read-feeds yes\nshow-read-articles {show_read}\nconfirm-exit no\narticle-sort-order guid-asc\n'+bindings+'\nbind g articlelist home\n'
                with reader(root,config,rss.as_uri()+'\n') as (_,screen,send,wait):
                    send('\n');wait(lambda s:'Item 00' in s)
                    send('nNnNnN')
                    wait(lambda s:'Item 06' in screen.display[screen.cursor.y])
                    if show_read=='yes':
                        send('g');wait(lambda s:'Item 00' in screen.display[screen.cursor.y])
                    send('nN'*10+'q')
                    wait(lambda s:'Your feeds' in s)
                    with sqlite3.connect(root/'cache') as db:
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM rss_item WHERE unread=1').fetchone()[0],0)
