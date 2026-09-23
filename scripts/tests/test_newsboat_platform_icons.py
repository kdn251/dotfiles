"""Check platform logos in the real feed list and mixed article list."""
import fcntl
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
import pyte

BINARY = Path(os.environ.get('NEWSBOAT_PAGED_BINARY', Path.home()/'.local/lib/newsboat-paged/newsboat'))

@unittest.skipUnless(BINARY.exists(), 'requires custom Newsboat')
class PlatformIconsTests(unittest.TestCase):
    def test_feed_and_article_source_logos(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            urls = ['"query:Mixed:title =~ \\"Video\\""']
            for name, site, link in [('YT', 'https://www.youtube.com/@creator', 'https://www.youtube.com/watch?v=abc123DEF45'), ('TW', 'https://twitch.tv/creator', 'https://twitch.tv/videos/123')]:
                feed = root/(name+'.xml')
                feed.write_text(f'<rss version="2.0"><channel><title>{name}</title><link>{site}</link><description>Test</description><item><title>Video {name}</title><link>{link}</link><guid>{name}</guid></item></channel></rss>')
                urls.append(feed.as_uri())
            (root/'status.feeds').write_text(f'{(root/"YT.xml").as_uri()}\t \n{(root/"TW.xml").as_uri()}\t \n')
            (root/'urls').write_text('\n'.join(urls)+'\n')
            (root/'config').write_text('show-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nfeedlist-format "%t"\narticlelist-format "%T %t"\n')
            args = [str(BINARY), '-C', str(root/'config'), '-u', str(root/'urls'), '-c', str(root/'cache')]
            subprocess.run(args+['-x','reload'], check=True, capture_output=True)
            pid, fd = pty.fork()
            if pid == 0:
                os.environ['TERM'] = 'xterm-256color'
                os.environ['NEWSBOAT_DOWNLOAD_STATUS'] = str(root/'status')
                os.execv(str(BINARY), args)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH',24,100,0,0))
            screen = pyte.Screen(100,24)
            stream = pyte.ByteStream(screen)
            def wait_logos(article=False):
                deadline = time.monotonic()+5
                while time.monotonic() < deadline:
                    if select.select([fd], [], [], .05)[0]: stream.feed(os.read(fd,65536))
                    output = '\n'.join(screen.display)
                    if all(x in output for x in (' YT', ' TW')) and (not article or 'Video YT' in output): return
                self.fail(output)
            try:
                wait_logos()
                os.write(fd,b'\n')
                wait_logos(article=True)
            finally:
                os.kill(pid,signal.SIGTERM)
                os.waitpid(pid,0)
                os.close(fd)
