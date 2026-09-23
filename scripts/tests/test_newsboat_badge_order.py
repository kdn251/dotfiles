"""Each saved list puts its own badge first without losing other badges."""
import fcntl, json, os, pty, select, signal, struct, subprocess, tempfile, termios, time, unittest
from pathlib import Path
try:
    import pyte
except ImportError:
    pyte = None
BINARY=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.local/lib/newsboat-paged/newsboat'))

@unittest.skipUnless(pyte and BINARY.exists(),'requires custom Newsboat and pyte')
class BadgeOrderTests(unittest.TestCase):
    def test_current_collection_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);feed=root/'feed.xml';url='https://example.com/video'
            feed.write_text(f'<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description><item><title>Video</title><link>{url}</link><guid>1</guid></item></channel></rss>')
            names=['⭐ Starred','📥 Downloads','📣 Commentary','📬 New']
            (root/'urls').write_text('\n'.join(json.dumps('query:'+n+':title = "Video"',ensure_ascii=False) for n in names)+'\n'+feed.as_uri()+'\n')
            (root/'config').write_text('show-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\narticlelist-format "%p %t"\n')
            (root/'stars').write_text(url+'\n');(root/'stars.commentary').write_text(url+'\n');(root/'downloads').write_text(url+'\t📥\n')
            args=[str(BINARY),'-C',str(root/'config'),'-u',str(root/'urls'),'-c',str(root/'cache')]
            subprocess.run(args+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(TERM='xterm-256color',NEWSBOAT_STARRED_STATUS=str(root/'stars'),NEWSBOAT_DOWNLOAD_STATUS=str(root/'downloads'))
                os.environ.pop('NEWSBOAT_NESTED_VIEWS',None)
                os.execv(str(BINARY),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            screen=pyte.Screen(100,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                end=time.monotonic()+5
                while time.monotonic()<end:
                    if select.select([fd],[],[],.03)[0]:stream.feed(os.read(fd,65536))
                    if predicate():return
                self.fail('\n'.join(screen.display))
            try:
                wait(lambda:'Your feeds' in screen.display[0])
                for i,expected in enumerate(['󰓎 📥 📣','📥 󰓎 📣','📣 󰓎 📥','󰓎 📥 📣'],1):
                    os.write(fd,f':{i}\n\n'.encode())
                    wait(lambda:expected in screen.display[1])
                    os.write(fd,b'q');wait(lambda:'Your feeds' in screen.display[0])
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
