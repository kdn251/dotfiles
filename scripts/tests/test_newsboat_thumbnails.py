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

    def test_video_links_and_shared_owner(self):
        for url,expected in [
            ('https://youtu.be/abc123DEF45','abc123DEF45'),
            ('https://www.youtube.com/shorts/abc123DEF45','abc123DEF45'),
            ('https://www.twitch.tv/videos/12345','twitch:12345'),
            ('https://clips.twitch.tv/TestClip','twitch-clip:TestClip'),
            ('https://www.twitch.tv/creator','twitch-live:creator')]:
            self.assertEqual(thumbs.selection('82;1;38;21;'+url)[4],expected)
        env={'NEWSBOAT_THUMBNAIL_OWNER':'1','KITTY_WINDOW_ID':'1'}
        with patch.object(thumbs.subprocess,'call',return_value=0) as call:
            thumbs.run(['newsboat'],env)
            self.assertEqual(call.call_args.kwargs['env']['NEWSBOAT_THUMBNAILS'],'1')

    def test_session_previews_mixed_items_and_saved_views(self):
        import shutil
        binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
        if not binary.exists():self.skipTest('custom Newsboat required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config_dir=root/'.newsboat';config_dir.mkdir()
            bindir=root/'.local/lib/newsboat-paged';bindir.mkdir(parents=True);(bindir/'newsboat').symlink_to(binary)
            images=root/'state/newsboat/youtube-playlists/thumbnails';images.mkdir(parents=True)
            Image.new('RGB',(320,180),'red').save(images/'abc123DEF45.png')
            Image.new('RGB',(320,180),'blue').save(images/'twitch:12345.png')
            rss=root/'feed.xml'
            rss.write_text('<rss version="2.0"><channel><title>Mixed items</title><link>https://example.com</link><description>test</description>'+
                ''.join(f'<item><title>{name}</title><guid>{i}</guid><link>{url}</link></item>' for i,(name,url) in enumerate([
                    ('YouTube video','https://youtu.be/abc123DEF45'),('Article','https://example.com/article'),
                    ('Twitch video','https://www.twitch.tv/videos/12345')]))+'</channel></rss>')
            config=config_dir/'config';urls=config_dir/'urls';urls.write_text(rss.as_uri()+'\n')
            config.write_text('show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-title-format "MIXED"\nrun-on-startup open\nbind-key j down\nbind-key k up\nbind R feedlist,articlelist reload-all\nbind h everywhere set browser "newsboat-home://show"\nbind t everywhere set browser "newsboat-starred://show"\n')
            subprocess.run([str(binary),'-C',str(config),'-u',str(urls),'-c',str(config_dir/'cache.db'),'-x','reload'],capture_output=True,check=True)
            saved_config=root/'saved-config';saved_config.write_text(config.read_text().replace('"MIXED"','"SAVED"'))
            shutil.copy(config_dir/'cache.db',root/'saved-cache')
            wrapper=root/'newsboat-session.py';shutil.copy(SCRIPTS/'newsboat-session.py',wrapper)
            (root/'newsboat-starred.py').write_text('import subprocess\nsubprocess.call('+repr([str(binary),'-C',str(saved_config),'-u',str(urls),'-c',str(root/'saved-cache')])+')\n')
            env=dict(os.environ,HOME=directory,XDG_STATE_HOME=str(root/'state'),TERM='xterm-256color',KITTY_WINDOW_ID='1')
            for key in list(env):
                if key.startswith('NEWSBOAT_') or key in {'TMUX','STY'}:env.pop(key)
            pid,fd=pty.fork()
            if pid==0:
                fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,1200,480))
                os.execve(sys.executable,[sys.executable,str(wrapper)],env)
            data=bytearray()
            def until(needle):
                end=time.monotonic()+6
                while time.monotonic()<end:
                    if needle in data:return
                    if select.select([fd],[],[],.05)[0]:
                        try:data.extend(os.read(fd,65536))
                        except OSError:break
                self.fail(repr(bytes(data[-700:])))
            try:
                until(b'MIXED');until(b'a=p,')
                self.assertNotIn(thumbs.MARKER,data)
                data.clear();os.write(fd,b'R');until(b'feeds refreshed')
                data.clear();os.write(fd,b'j');until(b'\x1b[23;0t')
                self.assertNotIn(b'a=p,',data[data.index(b'\x1b[23;0t'):])  # Article clears preview.
                data.clear();os.write(fd,b'j');until(b'a=p,')
                data.clear();os.write(fd,b't');until(b'SAVED');until(b'a=p,')
                data.clear();os.write(fd,b'h');until(b'Your feeds');until(b'\x1b[23;0t')
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

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
