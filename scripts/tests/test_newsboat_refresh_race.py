"""Refresh workers must not render the list while the UI is navigating it."""
import fcntl
import http.server
import os
from pathlib import Path
import pty
import select
import signal
import struct
import tempfile
import termios
import threading
import time
import unittest

class RefreshRaceTests(unittest.TestCase):
    def test_parallel_refresh_while_scrolling_and_redrawing(self):
        binary=Path(os.environ.get('NEWSBOAT_TEST_BINARY',Path.home()/'.local/lib/newsboat-paged/newsboat'))
        if not binary.exists():self.skipTest('custom Newsboat required')
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                ident=int(self.path.strip('/'))
                content=(f'<rss version="2.0"><channel><title>Feed {ident}</title><link>https://example.com</link><description>test</description>'+
                         ''.join(f'<item><title>Article {i}</title><link>https://example.com/{ident}/{i}</link><guid>{ident}/{i}</guid></item>' for i in range(4))+'</channel></rss>').encode()
                self.send_response(200);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
            def log_message(self,*_):pass
        class Server(http.server.ThreadingHTTPServer):request_queue_size=128
        server=Server(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);config=root/'config';urls=root/'urls';log=root/'log'
                config.write_text('reload-threads 100\nshow-read-feeds yes\nconfirm-exit no\nbind-key j down\nbind-key k up\nbind R feedlist,articlelist reload-all\n')
                urls.write_text(''.join(f'http://127.0.0.1:{server.server_port}/{i}\n' for i in range(100)))
                pid,fd=pty.fork()
                if pid==0:
                    fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',30,120,0,0))
                    os.environ['TERM']='xterm-256color'
                    os.execv(str(binary),[str(binary),'-C',str(config),'-u',str(urls),'-c',str(root/'cache.db'),'-d',str(log),'-l','6'])
                os.set_blocking(fd,False)
                reaped=False
                try:
                    # Give the first screen time to initialize.
                    time.sleep(.2)
                    for repeat in range(5):
                        if repeat%2:os.write(fd,b'\n')
                        os.write(fd,b'R')
                        deadline=time.monotonic()+20
                        count=0
                        while time.monotonic()<deadline:
                            done,status=os.waitpid(pid,os.WNOHANG)
                            if done:
                                reaped=True
                                self.fail(f'Newsboat exited during concurrent refresh: {os.waitstatus_to_exitcode(status)}')
                            try:os.write(fd,b'jk\x0c')
                            except BlockingIOError:pass
                            if select.select([fd],[],[],.003)[0]:
                                try:os.read(fd,65536)
                                except OSError:self.fail('Newsboat terminal closed during refresh')
                            if count%20==0:
                                text=log.read_bytes() if log.exists() else b''
                                if text.count(b"ScopeMeasure: function `Reloader::reload_all' took ")>repeat:break
                            count+=1
                            time.sleep(.01)
                        else:self.fail('Parallel refresh did not finish')
                        if repeat%2:os.write(fd,b'q')
                    os.write(fd,b'q')
                finally:
                    if not reaped:
                        try:os.kill(pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                        os.waitpid(pid,0)
                    os.close(fd)
        finally:
            server.shutdown();server.server_close()
