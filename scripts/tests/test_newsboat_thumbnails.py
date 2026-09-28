"""Graphics framing and real playlist selection/resize/search regression checks."""
import fcntl
import importlib.util
import io
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest.mock import patch
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import newsboat_thumbnails as thumbs
spec = importlib.util.spec_from_file_location('playlist_ui', SCRIPTS/'newsboat-playlists.py')
ui = importlib.util.module_from_spec(spec); spec.loader.exec_module(ui)


class ThumbnailTests(unittest.TestCase):
    def test_marker_survives_every_split_without_changing_screen_bytes(self):
        marker = thumbs.MARKER+b'82;1;38;21;https://www.youtube.com/watch?v=abc123DEF45\x07'
        payload = b'\x1b[2Jbefore'+marker+b'after'
        for split in range(len(payload)+1):
            decoder = thumbs.Decoder()
            events = list(decoder.feed(payload[:split]))+list(decoder.feed(payload[split:]))
            self.assertEqual(b''.join(v for k,v in events if k=='screen'), b'\x1b[2Jbeforeafter')
            self.assertEqual([thumbs.selection(v) for k,v in events if k=='selection'], [(82,1,38,21,'abc123DEF45')])
            self.assertFalse(decoder.pending)

    def test_invalid_selection_and_nonkitty_fallback(self):
        for value in ('', '82;1;38;21;https://example.com/watch?v=abc123DEF45', '82;1;0;21;https://www.youtube.com/watch?v=abc123DEF45'):
            self.assertIsNone(thumbs.selection(value))
        with patch.object(thumbs.subprocess,'call',return_value=0) as call:
            self.assertEqual(thumbs.run(['newsboat'],{}),0)
            call.assert_called_once_with(['newsboat'],env={})
        self.assertFalse(thumbs.supported({'KITTY_WINDOW_ID':'1','TMUX':'session'}))

    def test_graphics_packets_and_geometry(self):
        out=io.BytesIO();Image.new('RGB',(320,180),'red').save(out,'PNG')
        data=out.getvalue()
        self.assertIn(b'a=t,f=100,i=42,q=2',thumbs.transmit(42,data))
        place=thumbs.placement(42,(82,1,38,21,'abc123DEF45'),struct.pack('HHHH',24,120,1200,480),data)
        self.assertIn(b'a=p,i=42,p=1',place)
        self.assertTrue(place.startswith(b'\x1b7'))
        self.assertIn(b'\x1b[3;',place)  # First row below the pane's top margin.
        self.assertTrue(place.endswith(b'\x1b8'))
        self.assertEqual(thumbs.delete(42),b'\x1b_Ga=d,d=I,i=42,q=2\x1b\\')

    def test_real_playlist_selection_search_resize_and_cleanup(self):
        binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
        if not binary.exists():self.skipTest('custom Newsboat required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);library=root/'library';(library/'thumbnails').mkdir(parents=True)
            for ident,color in [('abc123DEF45','red'),('abc123DEF46','blue')]:
                Image.new('RGB',(320,180),color).save(library/'thumbnails'/(ident+'.png'))
            rows=[dict(title='First video',source='Creator',url='https://www.youtube.com/watch?v=abc123DEF45'),dict(title='Second video',source='Creator',url='https://www.youtube.com/watch?v=abc123DEF46')]
            cmd,config=ui.prepare_view(root,dict(kind='playlist',name='Preview test',rows=rows))
            subprocess.run(cmd+['-x','reload'],check=True,capture_output=True)
            with config.open('a') as out:out.write('run-on-startup open\n')
            env=dict(os.environ,TERM='xterm-256color',KITTY_WINDOW_ID='1')
            env.pop('TMUX',None);env.pop('STY',None)
            with patch.object(thumbs,'LIBRARY',library):
                pid,fd=pty.fork()
                if pid==0:
                    fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,1200,480))
                    os._exit(thumbs.run(cmd,env))
            data=bytearray()
            def until(needle):
                end=time.monotonic()+5
                while time.monotonic()<end:
                    if needle in data:return
                    if select.select([fd],[],[],.05)[0]:
                        try:data.extend(os.read(fd,65536))
                        except OSError:break
                self.fail(repr(bytes(data[-500:])))
            image_id=0x40000000+pid
            try:
                until(b'a=p,')
                self.assertIn(b'\x1b[22;0t\x1b]2;Newsboat Playlist Preview\x07',data)
                self.assertNotIn(thumbs.MARKER,data)
                data.clear();os.write(fd,b'j');until(b'a=t,')
                self.assertIn(thumbs.delete(image_id),data)
                data.clear();os.write(fd,b'/First\n');until(b'Search results');until(b'a=p,')
                data.clear();os.write(fd,b'?');until(b'Help');until(thumbs.delete(image_id))
                data.clear();os.write(fd,b'q');until(b'a=p,')
                data.clear();fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,800,480));os.kill(pid,signal.SIGWINCH)
                until(thumbs.delete(image_id))
                # Return to a wide window and verify the image is restored.
                time.sleep(.15);data.clear();fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,1200,480));os.kill(pid,signal.SIGWINCH)
                until(b'a=p,')
                data.clear();os.write(fd,b'q');time.sleep(.1);os.write(fd,b'q');until(b'\x1b[23;0t')
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
