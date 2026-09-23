"""Run with: python3 -m unittest discover -s scripts/tests -v"""
import errno
import fcntl
import http.server
import importlib.util
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'newsboat-session.py'
spec = importlib.util.spec_from_file_location('newsboat_session', SCRIPT)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class ProgressTests(unittest.TestCase):
    def test_compact_renderer_stays_in_footer(self):
        for frame in (0, 6, 22):
            output = session.Renderer.compact(frame, '2/5 feeds refreshed', 80, 24, 6)
            self.assertEqual(re.findall(rb'\x1b\[(\d+);1H', output),
                             [str(row).encode() for row in range(19, 25)])
            self.assertNotIn(b'\x1b[2J', output)
            self.assertIn(b'2/5 feeds refreshed', output)
            self.assertTrue(output.startswith(b'\x1b7'))
            self.assertTrue(output.endswith(b'\x1b8'))

    def test_counts_completions_not_starts_and_defers_queries(self):
        p = session.Progress()
        p.log(session.RELOAD_START)
        p.total = 4
        p.log(b'Reloader::reload: starting reload of https://example.com')
        self.assertEqual(p.caption(), '0/4 feeds refreshed')
        p.log(session.FEED_DONE + b'0.1 s')
        self.assertEqual(p.caption(), '1/4 feeds refreshed')
        p.log(b'Reloader::reload: skipping query feed')
        self.assertEqual(p.caption(), '1/4 feeds refreshed')
        p.log(session.FEED_DONE + b'0.0 s')
        self.assertEqual(p.caption(), '1/4 feeds refreshed')
        p.log(b'USERERROR: Error while retrieving a feed')
        p.log(session.FEED_DONE + b'0.2 s')
        p.log(session.FEED_DONE + b'0.3 s')
        p.log(session.BATCH_DONE[0] + b'0.7 s')
        self.assertEqual(p.caption(), '4/4 feeds checked (1 failed)')
        p.log(session.RELOAD_START)
        self.assertEqual(p.completed, 0)
        self.assertFalse(p.finished)

    def test_renderer_keeps_water_fixed(self):
        command = ''.join(f'{f}\t2/5 feeds refreshed\t80\t24\n' for f in (0, 6, 22))
        result = subprocess.run(['bash', str(SCRIPT.with_name('newsboat-launch.sh')), '--render'],
                                input=command.encode(), capture_output=True, check=True)
        self.assertEqual(result.stderr, b'')
        frames = [session.CSI.sub(b'', f).splitlines() for f in result.stdout.split(b'\0')[:-1]]
        hulls = [next(i for i, row in enumerate(f) if b'\\______________________/' in row) for f in frames]
        water = [tuple(i for i, row in enumerate(f) if b'~' in row) for f in frames]
        self.assertEqual(hulls, [hulls[0], hulls[0] - 1, hulls[0]])
        self.assertEqual(water, [water[0]] * 3)
        self.assertEqual(water[0][0] - hulls[0], 1)


class FeedServer(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        number = int(self.path.strip('/'))
        time.sleep(0.25 + number * 0.12)
        if number == getattr(self.server, 'fail_feed', None):
            self.send_error(503, 'Test refresh failure')
            return
        xml = f'''<?xml version="1.0"?><rss version="2.0"><channel>
<title>Test feed {number}</title><link>https://example.com</link><description>test</description>
<item><title>Test article {number}</title><link>https://example.com/{number}</link>
<guid>item-{number}</guid><description>test content</description></item></channel></rss>'''.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/rss+xml')
        self.send_header('Content-Length', str(len(xml)))
        self.end_headers()
        self.wfile.write(xml)

    def log_message(self, *_):
        pass


@unittest.skipUnless(shutil.which('newsboat'), 'requires Newsboat')
class TerminalIntegrationTests(unittest.TestCase):
    def test_closed_terminal_releases_newsboat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config'
            config.write_text('show-read-feeds yes\n')
            urls = root / 'urls'
            urls.write_text('https://example.com/feed\n')
            pid, fd = pty.fork()
            if pid == 0:
                os.environ.update(HOME=directory, TERM='xterm-256color')
                os.execv('/bin/bash', ['bash', str(SCRIPT.with_name('newsboat-launch.sh')),
                                      '-C', str(config), '-u', str(urls), '-c', str(root/'cache.db')])
            try:
                captured = b''
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and b'example.com' not in captured:
                    if select.select([fd], [], [], .1)[0]:
                        captured += os.read(fd, 65536)
                self.assertIn(b'example.com', captured)
                children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
                os.close(fd)
                fd = None
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    done, _ = os.waitpid(pid, os.WNOHANG)
                    if done:
                        pid = None
                        break
                    time.sleep(.05)
                self.assertIsNone(pid, 'launcher remained alive after terminal closed')
                self.assertFalse(any(Path(f'/proc/{child}').exists() for child in children))
            finally:
                if fd is not None:
                    os.close(fd)
                if pid:
                    os.kill(pid, signal.SIGTERM)
                    os.waitpid(pid, 0)

    def test_real_refresh_counter_repeat_and_browser(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FeedServer)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / 'config'
                config.write_text('reload-threads 3\nshow-read-feeds yes\n'
                                  'browser "sh -c \'printf BROWSER_OPEN; sleep 0.2\' -- %u"\n')
                urls = root / 'urls'
                urls.write_text(''.join(f'http://127.0.0.1:{server.server_port}/{i}\n' for i in range(6))
                                + '\"query:All:title =~ \\\"Test\\\"\"\n')
                pid, fd = pty.fork()
                if pid == 0:
                    os.environ.update(HOME=directory, TERM='xterm-256color')
                    os.execv('/bin/bash', ['bash', str(SCRIPT.with_name('newsboat-launch.sh')),
                                          '-C', str(config), '-u', str(urls), '-c', str(root / 'cache.db')])
                worker.start()
                fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
                captured = bytearray()

                def until(predicate, timeout=15):
                    end = time.monotonic() + timeout
                    while time.monotonic() < end:
                        if predicate(bytes(captured)):
                            return
                        if select.select([fd], [], [], 0.05)[0]:
                            try:
                                data = os.read(fd, 65536)
                            except OSError as error:
                                if error.errno == errno.EIO:
                                    break
                                raise
                            if not data:
                                break
                            captured.extend(data)
                    self.fail('Expected terminal event did not arrive. Tail: ' + repr(bytes(captured[-1800:])))

                try:
                    until(lambda data: b'Total:' in data or b'0 unread' in data or b'http://127.' in data)
                    for repeat in range(2):
                        captured.clear()
                        server.fail_feed = 5 if repeat else None
                        if repeat:
                            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
                        os.write(fd, b'R')
                        final = b'7/7 feeds checked (1 failed)' if repeat else b'7/7 feeds refreshed'
                        until(lambda data: b'feeds refreshed' in data)
                        os.write(fd, b'?')
                        until(lambda data: b'Help' in data)
                        self.assertNotIn(final, captured, 'input was blocked until refresh finished')
                        os.write(fd, b'q')
                        until(lambda data: final in data)
                        counts = [int(v) for v in re.findall(rb'(\d+)/7 feeds (?:refreshed|checked)', captured)]
                        self.assertTrue(any(0 < count < 7 for count in counts), counts)
                        self.assertEqual(counts, sorted(counts))
                        # Wait for the final animation frame to hand back to the feed list.
                        until(lambda data: b'Test feed' in data[data.rfind(final):])
                    captured.clear()
                    os.write(fd, b'o')
                    until(lambda data: b'BROWSER_OPEN' in data)
                    self.assertNotIn(b'feeds refreshed', captured)
                    self.assertNotIn(b'setting sail', captured)
                    time.sleep(0.3)
                    os.write(fd, b'Q')
                    until(lambda data: data.endswith(b'\x1b[0m\x1b[?1049l\x1b[?25h'))
                    _, status = os.waitpid(pid, 0)
                    pid = None
                    self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                finally:
                    if pid:
                        os.kill(pid, signal.SIGTERM)
                        os.waitpid(pid, 0)
                    os.close(fd)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
