"""Native paging regression test (requires optional pyte and the local build)."""
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

try:
    import pyte
except ImportError:
    pyte = None

BINARY = Path(os.environ.get('NEWSBOAT_PAGED_BINARY', Path.home()/'.local/lib/newsboat-paged/newsboat'))


@unittest.skipUnless(pyte and BINARY.exists(), 'requires pyte and paged Newsboat build')
class PagingTests(unittest.TestCase):
    def test_boundary_reverse_and_short_final_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root/'config'
            config.write_text('show-read-feeds yes\nfeedlist-format "%t"\nbind-key j down\nbind-key k up\nconfirm-exit no\n')
            urls = root/'urls'
            urls.write_text(''.join(f'"query:Row{i:03}:title = \\"none\\""\n' for i in range(1, 51)))
            pid, fd = pty.fork()
            if pid == 0:
                os.environ.update(TERM='xterm-256color', NEWSBOAT_PAGE_SCROLL='1', HOME=directory)
                os.execv(str(BINARY), [str(BINARY), '-q', '-C', str(config), '-u', str(urls), '-c', str(root/'cache')])
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
            screen = pyte.Screen(80, 24)
            stream = pyte.ByteStream(screen)

            def wait_for(predicate):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if select.select([fd], [], [], .05)[0]:
                        stream.feed(os.read(fd, 65536))
                    if predicate():
                        return
                self.fail('\n'.join(screen.display))

            try:
                wait_for(lambda: 'Row001' in screen.display[1])
                height = sum(line.strip().startswith('Row') for line in screen.display)
                self.assertGreater(height, 1)
                os.write(fd, b'j' * (height - 1))
                wait_for(lambda: screen.cursor.y == height)
                self.assertEqual(screen.display[1].strip(), 'Row001')
                os.write(fd, b'j')
                wait_for(lambda: screen.display[1].strip() == f'Row{height + 1:03}')
                self.assertEqual(screen.cursor.y, 1)
                os.write(fd, b'k')
                wait_for(lambda: screen.display[1].strip() == 'Row001')
                self.assertEqual(screen.cursor.y, height)
                os.write(fd, b'j' * (height + 1))
                wait_for(lambda: screen.display[1].strip() == f'Row{2 * height + 1:03}')
                self.assertEqual(screen.cursor.y, 1)
                self.assertTrue(any(not line.strip() for line in screen.display[2:height + 1]))
            finally:
                os.kill(pid, signal.SIGTERM)
                os.waitpid(pid, 0)
                os.close(fd)
