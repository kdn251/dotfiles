"""Full-title hover metadata, mouse framing, and non-destructive tooltips."""
import fcntl
import io
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
import newsboat_thumbnails as thumbnails
import newsboat_title_hover as hover
from test_newsboat_reconnect import BINARY

SIZE = struct.pack('HHHH', 20, 100, 1000, 400)


class HoverTests(unittest.TestCase):
    def test_split_mouse_reports_and_normal_keyboard(self):
        report = b'\x1b[<35;31;4M'
        for split in range(len(report)+1):
            instance = hover.Hover(77)
            instance.update('20;3;90;This is the full title\n')
            self.assertEqual(instance.feed(report[:split])+instance.feed(report[split:]), b'')
            self.assertEqual(instance.target[-1], 'This is the full title')
            self.assertEqual(instance.feed(b'jk\x1b[A'), b'jk\x1b[A')
            self.assertIsNone(instance.target)
        self.assertEqual(instance.feed(b'\x1b[<65;31;4M'), b'\x1b[B')
        self.assertEqual(instance.feed(b'\x1b[<64;31;4M'), b'\x1b[A')
        self.assertEqual(instance.feed(b'\x1b'), b'')
        with patch.object(hover.time, 'monotonic', return_value=time.monotonic()+1):
            self.assertEqual(instance.flush_input(), b'\x1b')

    def test_delay_movement_and_keyboard_cleanup(self):
        instance = hover.Hover(77)
        instance.update('20;3;90;This is a very long title that is truncated in the row\n')
        self.assertEqual(instance.render(SIZE), hover.ENABLE)
        instance.feed(b'\x1b[<35;31;4M')
        self.assertEqual(instance.render(SIZE), b'')
        with patch.object(hover.time, 'monotonic', return_value=time.monotonic()+1):
            drawn = instance.render(SIZE)
            self.assertIn(b'a=t,f=100,i=77', drawn)
            self.assertIn(b'z=20', drawn)
            self.assertNotIn(b'\x1b[2J', drawn)
            self.assertEqual(instance.render(SIZE), b'')
        instance.feed(b'j')
        self.assertIn(thumbnails.delete(77), instance.render(SIZE))
        instance.update('')
        self.assertEqual(instance.render(SIZE), hover.DISABLE)

    def test_tooltip_is_opaque_and_wraps(self):
        png, width, height = hover.picture('A detailed video title — '+('a long word ' * 24), SIZE)
        image=Image.open(io.BytesIO(png))
        self.assertEqual(image.getpixel((image.width//2,image.height//2))[3],255)
        self.assertLessEqual(width,100)
        self.assertGreater(height,2)
        self.assertLess(height,20)

    def test_title_marker_split_and_semicolons(self):
        marker=thumbnails.MARKER+b'titles;20;3;90;Title; with punctuation\n\x07'
        for split in range(len(marker)+1):
            decoder=thumbnails.Decoder()
            events=list(decoder.feed(marker[:split]))+list(decoder.feed(marker[split:]))
            self.assertEqual(events,[('titles','20;3;90;Title; with punctuation\n')])

    @unittest.skipUnless(BINARY.exists(), 'requires patched Newsboat')
    def test_native_emits_full_title_at_displayed_coordinates(self):
        self.check_native()

    @unittest.skipUnless(BINARY.exists(), 'requires patched Newsboat')
    def test_relay_handles_hover_without_sending_mouse_to_newsboat(self):
        self.check_native(relay=True)

    def check_native(self, relay=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            title='Long title '+('with all the details ' * 10)
            (root/'feed.xml').write_text('<rss version="2.0"><channel><title>Example</title><link>https://example.org</link><description>test</description><item><title>'+title+'</title><guid>1</guid><link>https://example.org/long</link></item><item><title>Short</title><guid>2</guid><link>https://example.org/short</link></item></channel></rss>')
            (root/'urls').write_text((root/'feed.xml').as_uri()+'\n')
            (root/'config').write_text('show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-format "%4i %t"\nrun-on-startup open\n')
            args=[str(BINARY),'-C',str(root/'config'),'-u',str(root/'urls'),'-c',str(root/'cache')]
            subprocess.run(args+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                fcntl.ioctl(0,termios.TIOCSWINSZ,SIZE)
                if relay:
                    import newsboat_playlist_avatars
                    newsboat_playlist_avatars.fetch_avatar = lambda _: None
                    thumbnails.background_opacity = lambda _: 1.0
                    env = dict(os.environ,TERM='xterm-256color',KITTY_WINDOW_ID='999999')
                    env.pop('NEWSBOAT_THUMBNAIL_OWNER',None)
                    try:
                        result = thumbnails.run(args,env)
                    except SystemExit:
                        result = 0
                    os._exit(result)
                os.execve(str(BINARY),args,dict(os.environ,TERM='xterm-256color',NEWSBOAT_THUMBNAILS='1'))
            decoder=thumbnails.Decoder();screen=pyte.Screen(100,20);stream=pyte.ByteStream(screen)
            rows=[]
            raw=bytearray()
            def read():
                nonlocal rows
                deadline=time.monotonic()+.5
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.02)[0]:
                        data=os.read(fd,65536)
                        raw.extend(data)
                        for kind,value in decoder.feed(data):
                            if kind=='screen':stream.feed(value)
                            elif kind=='titles':rows=hover.parse_rows(value)
            try:
                read()
                if relay:
                    self.assertIn(hover.ENABLE,raw)
                    image_id=0x40200000+pid
                    raw.clear()
                    os.write(fd,b'\x1b[<35;12;2M')
                    read();read()
                    self.assertIn(f'a=t,f=100,i={image_id}'.encode(),raw)
                    self.assertIn(b'z=20',raw)
                    raw.clear()
                    os.write(fd,b'j')
                    read()
                    self.assertIn(thumbnails.delete(image_id),raw)
                    os.write(fd,b'?')
                    raw.clear();read()
                    self.assertIn(hover.DISABLE,raw)
                    return
                self.assertEqual(len(rows),1)
                left,top,right,full=rows[0]
                self.assertEqual(full,title.rstrip())
                self.assertEqual(screen.display[top].index('Long title'),left)
                self.assertEqual(right,100)
                os.write(fd,b'?');read();self.assertEqual(rows,[])
                os.write(fd,b'q');read();self.assertEqual(len(rows),1)
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
