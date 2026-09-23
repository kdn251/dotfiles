"""A stalled feed server must not prevent opening local Downloads."""
import fcntl
import http.server
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
BINARY=Path.home()/'.local/lib/newsboat-paged/newsboat'

@unittest.skipUnless(BINARY.exists(), 'requires custom Newsboat')
class OfflineTests(unittest.TestCase):
    def test_stalled_server_opens_cached_downloads_within_budget(self):
        release=threading.Event()
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self): release.wait(12)
            def log_message(self,*args): pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.daemon_threads=True
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d); home=root/'.newsboat';home.mkdir()
                localbin=root/'.local/lib/newsboat-paged';localbin.mkdir(parents=True)
                (localbin/'newsboat').symlink_to(BINARY)
                feed=root/'feed.xml'
                feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description><item><title>Offline video</title><link>https://example.com/video</link><guid>1</guid></item></channel></rss>')
                (home/'urls').write_text('"query:📥 Downloads:title =~ \\"Offline\\""\n'+feed.as_uri()+'\n')
                config=home/'config';config.write_text('show-read-feeds yes\n')
                subprocess.run([str(BINARY),'-C',str(config),'-u',str(home/'urls'),'-c',str(home/'cache.db'),'-x','reload'],check=True,capture_output=True)
                config.write_text('urls-source miniflux\nshow-read-feeds yes\n')
                (home/'miniflux_creds.conf').write_text(f'miniflux-url "http://127.0.0.1:{server.server_port}"\nminiflux-login test\nminiflux-password test\n')
                started=time.monotonic();pid,fd=pty.fork()
                if pid==0:
                    os.environ.update(HOME=d,TERM='xterm-256color',XDG_STATE_HOME=str(root/'state'),NEWSBOAT_MINIFLUX_CONFIG=str(home/'miniflux_creds.conf'))
                    os.execv('/usr/bin/python',['python',str(SCRIPTS/'newsboat-session.py')])
                fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
                try:
                    output=b''
                    while time.monotonic()-started < 8:
                        if select.select([fd],[],[],.05)[0]: output+=os.read(fd,65536)
                        if 'Downloads — offline'.encode() in output and b'Offline video' in output:break
                    self.assertIn('Downloads — offline'.encode(),output)
                    self.assertIn(b'Offline video',output)
                    self.assertLess(time.monotonic()-started,8)
                    os.write(fd,b'q')
                    deadline=time.monotonic()+3
                    while time.monotonic()<deadline:
                        done,status=os.waitpid(pid,os.WNOHANG)
                        if done:
                            pid=None;self.assertEqual(os.waitstatus_to_exitcode(status),0);break
                        time.sleep(.05)
                    self.assertIsNone(pid)
                finally:
                    if pid:
                        os.kill(pid,signal.SIGTERM);os.waitpid(pid,0)
                    os.close(fd)
        finally:
            release.set();server.shutdown();server.server_close()
