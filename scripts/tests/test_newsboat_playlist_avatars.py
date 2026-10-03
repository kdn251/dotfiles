"""Per-row avatar layout, offline reuse, and native scrolling/cleanup."""
import fcntl
import io
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from unittest.mock import patch
from PIL import Image
import pyte
import newsboat_playlist_avatars as avatars
import newsboat_thumbnails as thumbs
from test_newsboat_reconnect import BINARY


class AvatarTests(unittest.TestCase):
    def test_cached_avatar_never_needs_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'playthroughs').mkdir()
            channel='UC'+'a'*22
            (root/'playthroughs/PLone.json').write_text(json.dumps(dict(rows=[dict(channel_id=channel)])))
            cache=root/'.cache/yt-channel-avatars';cache.mkdir(parents=True)
            Image.new('RGB',(128,128),'red').save(cache/(channel+'.png'))
            with patch.object(avatars,'LIBRARY',root),patch.object(avatars.Path,'home',return_value=root),patch.object(avatars.subprocess,'run') as run:
                self.assertTrue(avatars.fetch_avatar('PLone'))
                run.assert_not_called()

    def test_square_fit_reorder_and_leave(self):
        image=io.BytesIO();Image.new('RGB',(128,128),'red').save(image,'PNG')
        size=struct.pack('HHHH',24,120,1200,576)
        fitted=Image.open(io.BytesIO(avatars.fit_avatar(image.getvalue(),size)))
        self.assertEqual(fitted.size,(20,24))
        self.assertEqual(fitted.getpixel((10,12)),(255,0,0,255))
        self.assertEqual(fitted.getpixel((0,0))[3],0)
        renderer=avatars.Avatars(500);renderer.started=True
        renderer.images={'PLa':image.getvalue(),'PLb':image.getvalue()}
        renderer.update('0;1;newsboat-playthroughs://PLa\n0;2;newsboat-playthroughs://PLb\n')
        first=renderer.render(size)
        self.assertIn(b'\x1b[2;1H',first);self.assertIn(b'\x1b[3;1H',first)
        self.assertEqual(renderer.render(size),b'')
        renderer.update('0;1;newsboat-playthroughs://PLb\n')
        output=renderer.render(size)
        self.assertIn(thumbs.delete(500),output);self.assertIn(thumbs.delete(501),output)
        renderer.update('')
        self.assertEqual(renderer.render(size),thumbs.delete(500))
        self.assertEqual(renderer.displayed,{})

    def test_marker_can_be_split_anywhere(self):
        payload=thumbs.MARKER+b'avatars;0;1;newsboat-playthroughs://PLa\n\x07'
        for split in range(len(payload)+1):
            decoder=thumbs.Decoder()
            events=list(decoder.feed(payload[:split]))+list(decoder.feed(payload[split:]))
            self.assertEqual(events,[('avatars','0;1;newsboat-playthroughs://PLa\n')])

    @unittest.skipUnless(BINARY.exists(),'requires custom native Newsboat')
    def test_native_rows_follow_scroll_and_disappear_in_help(self):
        self.check_native_rows('Playlists · 🎮 Playthroughs', 'newsboat-playthroughs://PL', '%4i %4w %p %t')

    def test_starred_rows_include_automatic_number_and_progress_columns(self):
        self.check_native_rows('⭐ Starred', 'https://youtu.be/abc123DEF', '%f %-9p %t')

    def test_twitch_rows_and_search_keep_avatars_beside_titles(self):
        self.check_native_rows('🎬 VODs', 'https://www.twitch.tv/videos/12345', '%4i %4w %t')

    def check_native_rows(self, title, url_prefix, row_format):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rss=root/'feed.xml';config=root/'config';urls=root/'urls'
            rss.write_text('<rss version="2.0"><channel><title>'+title+'</title><link>https://example.org</link><description>test</description>'+''.join(
                f'<item><title>Series{i:02d}</title><guid>{i:02d}</guid><link>{url_prefix}{i:02d}</link></item>' for i in range(40))+'</channel></rss>')
            urls.write_text(rss.as_uri()+'\n')
            config.write_text('show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-format "'+row_format+'"\nrun-on-startup open\nbind-key j down\nbind-key G end\n')
            command=[str(BINARY),'-C',str(config),'-u',str(urls),'-c',str(root/'cache')]
            subprocess.run(command+['-x','reload'],capture_output=True,check=True)
            pid,fd=pty.fork()
            if pid==0:
                fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',16,120,1200,320))
                os.execve(str(BINARY),command,dict(os.environ,TERM='xterm-256color',NEWSBOAT_THUMBNAILS='1'))
            decoder=thumbs.Decoder();screen=pyte.Screen(120,16);stream=pyte.ByteStream(screen);rows=[]
            def read():
                nonlocal rows
                deadline=time.monotonic()+.4
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.02)[0]:
                        for kind,value in decoder.feed(os.read(fd,65536)):
                            if kind=='screen':stream.feed(value)
                            elif kind=='avatars':rows=[(x,y,'PL'+key.split('\t')[0][-2:]) for x,y,key in avatars.parse_rows(value)]
            def check():
                self.assertTrue(rows)
                for x,y,ident in rows:
                    title = 'Series'+ident[2:]
                    self.assertIn(title,screen.display[y])
                    self.assertEqual(screen.display[y].index(title),x+3)
                    self.assertEqual(int(screen.display[y].split()[0]),int(ident[2:])+1)
                    self.assertIn('0%',screen.display[y][:x])
            try:
                read();check();self.assertEqual(rows[0][2],'PL00')
                os.write(fd,b'/Series01\n');read()
                self.assertEqual(len(rows),1)
                x,y,ident=rows[0]
                self.assertEqual(ident,'PL01')
                self.assertEqual(screen.display[y].index('Series01'),x+3)
                os.write(fd,b'q');read();check()
                os.write(fd,b'j'*24);read();check();self.assertNotEqual(rows[0][2],'PL00')
                os.write(fd,b'G');read();check();self.assertEqual(rows[-1][2],'PL39')
                os.write(fd,b'?');read();self.assertEqual(rows,[])
                os.write(fd,b'q');read();check()
                fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',12,100,1000,240));os.kill(pid,signal.SIGWINCH)
                screen.resize(12,100);read();check();self.assertLessEqual(len(rows),10)
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
