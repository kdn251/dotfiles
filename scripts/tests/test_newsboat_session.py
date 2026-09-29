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
import sys
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
    def test_graphics_packets_stay_whole_before_toast_is_added(self):
        packet = b'\x1b_Ga=t,f=100,m=0;YWJj\x1b\\'
        for split in range(len(packet)+1):
            stream = session.GraphicsStream()
            first = stream.feed(b'before'+packet[:split])
            second = stream.feed(packet[split:]+b'after')
            self.assertEqual(first+second,b'before'+packet+b'after')
            self.assertTrue(packet in first or packet in second)

    def test_selection_and_remote_commands_stay_whole_before_toast(self):
        for packet in (b'\x1b]777;newsboat-thumbnail;82;1;38;21;https://youtu.be/abc123DEF45\x07',
                       b'\x1bP@kitty-cmd{"cmd":"set-background-opacity"}\x1b\\'):
            for split in range(len(packet)+1):
                stream=session.GraphicsStream()
                chunks=[stream.feed(packet[:split]),stream.feed(packet[split:])]
                self.assertEqual(b''.join(chunks),packet)
                self.assertIn(packet,chunks)

    def test_slide_uses_small_monotonic_steps(self):
        entering = [session.slide_offset(i/60, 34) for i in range(31)]
        leaving = [session.slide_offset(i/60, 34, exiting=True) for i in range(31)]
        self.assertEqual((entering[0], entering[-1]), (34, 0))
        self.assertEqual((leaving[0], leaving[-1]), (0, 34))
        self.assertEqual(entering, sorted(entering, reverse=True))
        self.assertEqual(leaving, sorted(leaving))
        self.assertGreater(len(set(entering)), 20)
        self.assertLessEqual(max(abs(a-b) for a,b in zip(entering, entering[1:])), 2)

    def test_graphics_toast_does_not_erase_underlying_rows(self):
        for offset in (0,8,33):
            output=session.Renderer.overlay(0,'2/5 feeds refreshed',80,24,9,offset)
            self.assertIn(b'z=2,',output)
            self.assertIn(f'c={34-offset},r=9'.encode(),output)
            self.assertNotIn(b'\x1b[0m',output)
            self.assertNotIn(f'\x1b[{34-offset}X'.encode(),output)
        self.assertEqual(session.Renderer.overlay(0,'done',80,24,9,34),session.Renderer.clear_overlay())

    def test_slide_clips_at_right_margin(self):
        for offset in (0, 8, 20, 33):
            output = session.Renderer.compact(0, '2/5 feeds refreshed', 80, 24, 9, offset)
            columns = re.findall(rb'\x1b\[\d+;(\d+)H', output)
            self.assertEqual(set(columns), {str(45 + offset).encode()})
            self.assertIn(f'\x1b[{34-offset}X'.encode(), output)
        self.assertEqual(session.Renderer.compact(0, 'done', 80, 24, 9, 34), b'')

    def test_summary_counts_new_items_and_distinct_sources(self):
        progress = session.Progress()
        progress.log(session.RELOAD_START + b' total feeds: 2')
        for source in (b'one', b'one', b'two'):
            progress.log(b'Newsboat refresh new item source: ' + source)
        progress.log(b'USERERROR: Feed failed')
        progress.log(session.BATCH_DONE[0])
        self.assertIn('3 new · 2 sources updated', progress.toast_caption())
        self.assertIn('1 failed', progress.toast_caption())
        progress.log(session.RELOAD_START)
        progress.log(session.BATCH_DONE[0])
        self.assertIn('0 new · 0 sources updated', progress.toast_caption())

    def test_total_is_available_before_first_feed_finishes(self):
        progress = session.Progress()
        progress.log(session.RELOAD_START + b' total feeds: 207')
        self.assertEqual(progress.caption(), '0/207 feeds refreshed')

    def test_compact_renderer_stays_in_top_right_toast(self):
        for frame in (0, 6, 22):
            output = session.Renderer.compact(frame, '2/5 feeds refreshed', 80, 24, 9)
            self.assertEqual(re.findall(rb'\x1b\[(\d+);45H', output),
                             [str(row).encode() for row in range(2, 11)])
            self.assertNotIn(b'\x1b[2J', output)
            self.assertIn(b'2/5 feeds refreshed', output)
            self.assertTrue(output.startswith(b'\x1b7'))
            self.assertTrue(output.endswith(b'\x1b8'))
            water = next(line for line in session.CSI.sub(b'', output).decode().split('│') if '~' in line)
            self.assertEqual(len(water), 32)

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
    def test_playlist_shortcut_opens_during_active_feed_refresh(self):
        gate=threading.Event();started=threading.Event()
        class BlockingFeed(FeedServer):
            def do_GET(self):
                if getattr(self.server,'block',False):
                    started.set();gate.wait(10)
                super().do_GET()
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),BlockingFeed)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                wrapper=root/'newsboat-session.py';shutil.copyfile(SCRIPT,wrapper)
                helper=root/'newsboat-playlists.py'
                helper.write_text('import os,sys,tty\nfrom pathlib import Path\n'
                    'if sys.argv[1]=="request":\n'
                    ' Path(os.environ["NEWSBOAT_PLAYLIST_REQUEST"]).write_text(sys.argv[2]);sys.exit(0)\n'
                    'tty.setraw(0);os.write(1,b"\\x1b[H\\x1b[2JPLAYLIST_DURING_REFRESH")\n'
                    'while os.read(0,1)!=b"q":pass\n')
                bindir=root/'.local/lib/newsboat-paged';bindir.mkdir(parents=True)
                binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
                (bindir/'newsboat').symlink_to(binary)
                config=root/'config';urls=root/'urls';cache=root/'cache.db'
                binding=next(line for line in SCRIPT.parents[2].joinpath('newsboat/.newsboat/config').read_text().splitlines() if line.startswith('bind P '))
                self.assertIn('request %u',binding)
                self.assertIn('open-in-browser-noninteractively',binding)
                binding=binding.replace('~/scripts/newsboat-playlists.py',str(helper))
                config.write_text('show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nbind R feedlist,articlelist,searchresultslist reload-all\n'+binding+'\n')
                urls.write_text(f'http://127.0.0.1:{server.server_port}/0\n')
                args=['-C',str(config),'-u',str(urls),'-c',str(cache)]
                subprocess.run([str(binary),*args,'-x','reload'],check=True,capture_output=True)
                env=dict(os.environ,HOME=directory,XDG_STATE_HOME=str(root/'state'),TERM='xterm-256color')
                pid,fd=pty.fork()
                if pid==0:os.execve(sys.executable,[sys.executable,str(wrapper),*args],env)
                fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
                captured=bytearray()
                def until(needle):
                    end=time.monotonic()+6
                    while time.monotonic()<end:
                        if needle in captured:return
                        if select.select([fd],[],[],.05)[0]:
                            try:captured.extend(os.read(fd,65536))
                            except OSError:break
                    self.fail(repr(bytes(captured[-1600:])))
                try:
                    until(b'Test feed 0');captured.clear();os.write(fd,b'\n')
                    until(b'Test article 0')
                    server.block=True;captured.clear();os.write(fd,b'R')
                    until(b'feeds refreshed');self.assertTrue(started.wait(1))
                    os.write(fd,b'P');until(b'PLAYLIST_DURING_REFRESH')
                    self.assertFalse(gate.is_set(),'playlist opening waited for refresh completion')
                    captured.clear();os.write(fd,b'q');until(b'Test article 0')
                    gate.set();until(b'1/1 feeds refreshed')
                finally:
                    gate.set();os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
        finally:
            gate.set();server.shutdown();server.server_close()

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
                wrapper = root / 'newsboat-session.py'
                shutil.copyfile(SCRIPT, wrapper)
                (root/'newsboat-launch.sh').symlink_to(SCRIPT.with_name('newsboat-launch.sh'))
                (root/'newsboat-starred.py').write_text(
                    'import os, tty\nfrom pathlib import Path\ntty.setraw(0)\n'
                    'os.write(1,b"\\x1b[H\\x1b[2JNESTED_VIEW")\n'
                    'while True:\n'
                    ' key=os.read(0,1)\n'
                    ' if key == b"q": break\n'
                    ' if key == b"P": Path(os.environ["NEWSBOAT_PLAYLIST_REQUEST"]).write_text("https://www.youtube.com/watch?v=abc123DEF45")\n'
                    ' if key == b"\\x0c": os.write(1,b"\\x1b[H\\x1b[2JNESTED_RESTORED")\n')
                (root/'newsboat-playlists.py').write_text(
                    'import os, tty\ntty.setraw(0)\n'
                    'os.write(1,b"\\x1b[H\\x1b[2JPLAYLIST_OVERLAY")\n'
                    'while os.read(0,1) != b"q": pass\n')
                binary = Path.home()/'.local/lib/newsboat-paged/newsboat'
                target = root/'.local/lib/newsboat-paged'
                target.mkdir(parents=True)
                (target/'newsboat').symlink_to(binary)

                config = root / 'config'
                config.write_text('reload-threads 3\nshow-read-feeds yes\n'
                                  'bind h everywhere set browser "newsboat-starred://show" ; set browser "sh -c \'printf BROWSER_OPEN; sleep 0.2\' -- %u"\n'
                                  'browser "sh -c \'printf BROWSER_OPEN; sleep 0.2\' -- %u"\n')
                urls = root / 'urls'
                urls.write_text(''.join(f'http://127.0.0.1:{server.server_port}/{i}\n' for i in range(6))
                                + '\"query:All:title =~ \\\"Test\\\"\"\n')
                pid, fd = pty.fork()
                if pid == 0:
                    os.environ.update(HOME=directory, TERM='xterm-256color')
                    os.execv(sys.executable, [sys.executable, str(wrapper),
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
                        self.assertNotIn(b'/? feeds', captured)
                        os.write(fd, b'?')
                        until(lambda data: b'Help' in data)
                        self.assertNotIn(final, captured, 'input was blocked until refresh finished')
                        os.write(fd, b'q')
                        os.write(fd, b'h')
                        until(lambda data: b'NESTED_VIEW' in data)
                        until(lambda data: final in data[data.find(b'NESTED_VIEW'):])
                        expected_summary = '0 new · 0 sources updated' if repeat else '6 new · 6 sources updated'
                        until(lambda data: expected_summary.encode() in data)
                        self.assertIn('╭'.encode(), captured[captured.find(b'NESTED_VIEW'):])
                        os.write(fd, b'P')
                        until(lambda data: b'PLAYLIST_OVERLAY' in data)
                        os.write(fd, b'q')
                        until(lambda data: b'NESTED_RESTORED' in data[data.find(b'PLAYLIST_OVERLAY'):])
                        os.write(fd, b'q')
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
