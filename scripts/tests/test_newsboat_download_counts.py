"""Exercise actual native query counts and selection across URL rewrites."""
import fcntl,os,pty,select,signal,struct,subprocess,tempfile,termios,time,unittest
from pathlib import Path
try:
    import pyte
except ImportError:
    pyte=None
BINARY=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.local/lib/newsboat-paged/newsboat'))

@unittest.skipUnless(pyte and BINARY.exists(),'requires pyte and local Newsboat build')
class DownloadCountsTests(unittest.TestCase):
    def test_return_idle_and_delete_update_counts_without_moving_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'config';urls=root/'urls';feed=root/'feed.xml'
            config.write_text('articlelist-format "%-9p %t"\nshow-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nfeedlist-format "%t | %U unread"\nconfirm-exit no\n')
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description>'+''.join(f'<item><title>Video{i}</title><link>https://example.com/{i}</link><guid>{i}</guid></item>' for i in [1,2])+'</channel></rss>')
            def update(expression):
                text='"query:📥 Downloads:'+expression.replace('"','\\"')+'"\n'+feed.as_uri()+'\n'
                temporary=root/'new';temporary.write_text(text);temporary.replace(urls)
            update('title = "none"')
            args=[str(BINARY),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache')]
            subprocess.run(args+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(TERM='xterm-256color',NEWSBOAT_LIVE_QUERIES=str(urls),HOME=directory,NEWSBOAT_DOWNLOAD_STATUS=str(root/'downloads.tsv'),NEWSBOAT_STARRED_STATUS=str(root/'stars.txt'))
                os.execv(str(BINARY),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            screen=pyte.Screen(100,24);stream=pyte.ByteStream(screen)
            def wait(text):
                deadline=time.monotonic()+7
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
                    if text in '\n'.join(screen.display):return
                self.fail('\n'.join(screen.display))
            try:
                wait('Downloads | 0 unread')
                os.write(fd,b':2\n\n');wait("Articles in feed 'Source'")
                (root/'downloads.tsv').write_text('https://example.com/1\t📥\n')
                (root/'stars.txt').write_text('https://example.com/1\n')
                wait('󰓎 📥')
                (root/'stars.txt').write_text('')
                deadline=time.monotonic()+4
                while '󰓎' in '\n'.join(screen.display) and time.monotonic()<deadline:
                    if select.select([fd],[],[],.1)[0]:stream.feed(os.read(fd,65536))
                self.assertNotIn('󰓎','\n'.join(screen.display))
                self.assertIn('📥','\n'.join(screen.display))
                update('title = "Video1"')
                os.write(fd,b'q');wait('Downloads | 1 unread')
                self.assertEqual(screen.cursor.y,2)
                update('title =~ "Video"');wait('Downloads | 2 unread')
                self.assertEqual(screen.cursor.y,2)
                update('title = "none"');wait('Downloads | 0 unread')
                self.assertEqual(screen.cursor.y,2)
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
