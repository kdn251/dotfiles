"""A stalled feed server must not prevent browsing the offline library."""
import fcntl
import http.server
import json
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
    def test_stalled_server_opens_offline_home_within_budget(self):
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
                saved=root/'state/newsboat/youtube-playlists/playthroughs'
                saved.mkdir(parents=True)
                (saved/'PLoffline.json').write_text(json.dumps(dict(schema=2,id='PLoffline',
                    name='Saved adventure',channel='Offline creator',selected_urls=['https://www.youtube.com/watch?v=abcdefghijk'],
                    rows=[dict(title='Episode one',url='https://www.youtube.com/watch?v=abcdefghijk',position=1,source='Offline creator')])) )
                started=time.monotonic();pid,fd=pty.fork()
                if pid==0:
                    os.environ.update(HOME=d,TERM='xterm-256color',XDG_STATE_HOME=str(root/'state'),NEWSBOAT_MINIFLUX_CONFIG=str(home/'miniflux_creds.conf'))
                    os.execv('/usr/bin/python',['python',str(SCRIPTS/'newsboat-session.py')])
                fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
                try:
                    output=b''
                    while time.monotonic()-started < 8:
                        if select.select([fd],[],[],.05)[0]:
                            try: output+=os.read(fd,65536)
                            except OSError: self.fail(output.decode(errors='replace'))
                        if 'Newsboat — offline'.encode() in output and b'Playthroughs' in output:break
                    self.assertIn('Newsboat — offline'.encode(),output)
                    self.assertIn(b'Downloads',output)
                    self.assertIn(b'Playthroughs',output)
                    self.assertLess(time.monotonic()-started,8)
                    os.write(fd,b'\r')
                    deadline=time.monotonic()+3
                    output=b''
                    while time.monotonic()<deadline:
                        if select.select([fd],[],[],.05)[0]:
                            try: output+=os.read(fd,65536)
                            except OSError: self.fail(output.decode(errors='replace'))
                        if b'Offline video' in output:break
                    self.assertIn(b'Offline video',output)
                    os.write(fd,b'q')
                    time.sleep(.2)
                    os.write(fd,b'j\r')
                    deadline=time.monotonic()+3
                    output=b''
                    while time.monotonic()<deadline:
                        if select.select([fd],[],[],.05)[0]: output+=os.read(fd,65536)
                        if b'Saved adventure' in output:break
                    self.assertIn(b'Saved adventure',output)
                    os.write(fd,b'\r')
                    deadline=time.monotonic()+4
                    output=b''
                    while time.monotonic()<deadline:
                        if select.select([fd],[],[],.05)[0]: output+=os.read(fd,65536)
                        if b'Episode one' in output:break
                    self.assertIn(b'Episode one',output)
                    os.write(fd,b'q')
                    time.sleep(.2)
                    os.write(fd,b'q')
                    time.sleep(.2)
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
