"""Playthrough progress sorting and selection stability in a real terminal."""
from pathlib import Path
import tempfile
import unittest
from test_newsboat_reconnect import reader, pyte, BINARY

@unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
class PlaythroughOrderTests(unittest.TestCase):
    def test_progress_descending_updates_without_changing_selected_playlist(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);feed=root/'feed.xml';status=root/'status';status.write_text('')
            watched=root/'status.watched'
            def progress(values):
                tmp=root/'progress.tmp';tmp.write_text(''.join(f'newsboat-playthroughs://PL{i}\t{p}%\n' for i,p in enumerate(values)))
                tmp.replace(watched)
            progress([0,25,90,100])
            feed.write_text('<rss version="2.0"><channel><title>Playlists · 🎮 Playthroughs</title><link>https://example.com</link><description>Test</description>'+''.join(f'<item><title>Series{i}</title><guid>{i}</guid><link>newsboat-playthroughs://PL{i}</link></item>' for i in range(4))+'</channel></rss>')
            config='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-format "%4w %t"\nbind-key j down\n'
            with reader(root,config,feed.as_uri()+'\n',{'NEWSBOAT_DOWNLOAD_STATUS':str(status)}) as (_,screen,send,wait):
                wait(lambda s:'Playthroughs' in s);send('\n')
                wait(lambda s:all('Series'+str(i) in s for i in range(4)))
                text='\n'.join(screen.display)
                self.assertLess(text.index('Series3'),text.index('Series2'))
                self.assertLess(text.index('Series2'),text.index('Series1'))
                self.assertLess(text.index('Series1'),text.index('Series0'))
                send('j');wait(lambda s:'Series2' in screen.display[screen.cursor.y])
                progress([0,95,90,100])
                wait(lambda s:s.index('Series1')<s.index('Series2'))
                self.assertIn('Series2',screen.display[screen.cursor.y])
