"""A slow player startup must not hold Newsboat's navigation loop."""
import fcntl, os, pty, select, shutil, signal, struct, subprocess, tempfile, termios, time, unittest
from pathlib import Path
try:
    import pyte
except ImportError:
    pyte = None
SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
BINARY = Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.local/lib/newsboat-paged/newsboat'))

@unittest.skipUnless(pyte and BINARY.exists(), 'requires native Newsboat and pyte')
class PlaybackTests(unittest.TestCase):
    def test_cursor_moves_before_player_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shutil.copyfile(SCRIPTS/'newsboat-play-video.py',root/'newsboat-play-video.py')
            player=root/'mpv-yt'
            player.write_text('#!/usr/bin/env python3\nimport os,time\nfrom pathlib import Path\ntime.sleep(2)\nPath(os.environ["NEWSBOAT_PLAY_READY"]).write_text("playing")\n')
            player.chmod(0o755)
            (root/'newsboat-history.py').write_text('from pathlib import Path\nPath(__file__).with_name("played").touch()\n')
            feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Videos</title>'+''.join(f'<item><title>Item{i}</title><link>https://example.com/{i}</link><guid>{i}</guid></item>' for i in (1,2))+'</channel></rss>')
            (root/'urls').write_text(feed.as_uri()+'\n')
            (root/'config').write_text('show-read-articles yes\narticle-sort-order title-asc\nbind-key j down\nbind o articlelist open-in-browser-noninteractively\nbrowser "python3 '+str(root/'newsboat-play-video.py')+' %u"\n')
            args=[str(BINARY),'-C',str(root/'config'),'-u',str(root/'urls'),'-c',str(root/'cache')]
            subprocess.run(args+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ['TERM']='xterm-256color';os.execv(str(BINARY),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            screen=pyte.Screen(100,24);stream=pyte.ByteStream(screen)
            def wait(predicate,timeout=5):
                end=time.monotonic()+timeout
                while time.monotonic()<end:
                    if select.select([fd],[],[],.02)[0]:stream.feed(os.read(fd,65536))
                    if predicate():return
                self.fail('\n'.join(screen.display))
            try:
                wait(lambda:'Videos' in '\n'.join(screen.display));os.write(fd,b'\n')
                wait(lambda:'Item2' in '\n'.join(screen.display))
                os.write(fd,b'oj');wait(lambda:screen.cursor.y==2,timeout=1)
                self.assertFalse((root/'played').exists())
                wait(lambda:(root/'played').exists())
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
