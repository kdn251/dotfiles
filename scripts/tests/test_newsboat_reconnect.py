"""Simulated network outage and incremental refresh, without suspending the laptop."""
from contextlib import contextmanager
import fcntl,json,os,pty,select,signal,struct,subprocess,tempfile,termios,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
try: import pyte
except ImportError: pyte=None
BINARY=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat'))

@contextmanager
def reader(root,config,urls,env=None):
    cfg=root/'config';cfg.write_text(config)
    file=root/'urls';file.write_text(urls)
    args=[str(BINARY),'-q','-C',str(cfg),'-u',str(file),'-c',str(root/'cache')]
    subprocess.run(args+['-x','reload'],check=True,capture_output=True,timeout=10)
    pid,fd=pty.fork()
    if pid==0:
        os.environ.update(HOME=str(root),TERM='xterm-256color',**(env or {}));os.execv(str(BINARY),args)
    fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',20,120,0,0))
    screen=pyte.Screen(120,20);stream=pyte.ByteStream(screen)
    def wait(predicate,timeout=5):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if select.select([fd],[],[],.02)[0]:stream.feed(os.read(fd,65536))
            if predicate('\n'.join(screen.display)):return
        raise AssertionError('\n'.join(screen.display))
    try:yield file,screen,lambda text:os.write(fd,text.encode()),wait
    finally:os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

@unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
class ReconnectTests(unittest.TestCase):
    def test_local_queries_do_not_request_miniflux_during_outage(self):
        calls=[];offline=False;release=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                calls.append(self.path)
                if offline:release.wait(8)
                if self.path=='/v1/me':body={}
                elif self.path=='/v1/categories':body=[dict(id=1,title='Category')]
                elif self.path=='/v1/feeds':body=[dict(id=1,title='Source',feed_url='https://example.org/rss',category=dict(id=1))]
                elif '/entries' in self.path:body=dict(entries=[dict(id=1,title='Item',url='https://example.org/1',author='Author',content='Body',published_at='2026-01-01T00:00:00Z',status='unread',enclosures=[])])
                else:body={}
                payload=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                try:self.wfile.write(payload)
                except (BrokenPipeError,ConnectionResetError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d)
                cfg=f'urls-source miniflux\nminiflux-url "http://127.0.0.1:{server.server_port}"\nminiflux-login test\nminiflux-password test\nminiflux-show-special-feeds no\nauto-reload no\nsuppress-first-reload yes\nshow-read-feeds yes\nprepopulate-query-feeds yes\nconfirm-exit no\ndownload-timeout 1\nfeedlist-format "%t %v"\nbind-key j down\n'
                urls='"query:📬 New:unread = \\"yes\\""\n'
                with reader(root,cfg,urls,dict(NEWSBOAT_LIVE_QUERIES=str(root/'urls'))) as (file,screen,send,wait):
                    wait(lambda s:'Source' in s);time.sleep(.2)
                    count=len(calls);offline=True
                    file.write_text(urls+'"query:LocalTest:unread = \\"yes\\""\n')
                    started=time.monotonic();wait(lambda s:'LocalTest' in s,1.5)
                    self.assertLess(time.monotonic()-started,1.5)
                    send('j');wait(lambda s:screen.cursor.y==2,1)
                    self.assertEqual(len(calls),count)
                    # Explicit refresh still reconnects, but a stalled metadata
                    # request times out and preserves the already-known feeds.
                    send('Rj');wait(lambda s:len(calls)>count)
                    wait(lambda s:screen.cursor.y==3 and 'Source' in s,2.5)
                    self.assertEqual(calls[count],'/v1/categories')
                    self.assertNotIn('/v1/feeds',calls[count:])
                    offline=False;release.set()
        finally:release.set();server.shutdown();server.server_close();thread.join()

    def test_new_count_changes_before_last_feed_finishes(self):
        phase=0;release=threading.Event();slow_started=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if phase and self.path=='/slow':slow_started.set();release.wait(8)
                name=self.path.strip('/')
                payload=('<rss version="2.0"><channel><title>'+name+'</title><link>https://example.org</link><description>test</description>'+''.join(f'<item><title>{name}{i}</title><guid>{name}{i}</guid><link>https://example.org/{name}{i}</link></item>' for i in range(phase+1))+'</channel></rss>').encode()
                self.send_response(200);self.end_headers()
                try:self.wfile.write(payload)
                except (BrokenPipeError,ConnectionResetError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);url=f'http://127.0.0.1:{server.server_port}'
                urls='"query:📬 New:unread = \\"yes\\""\n"query:🌎 All:unread = \\"yes\\""\n'+url+'/fast\n'+url+'/slow\n'
                cfg='auto-reload no\nsuppress-first-reload yes\nshow-read-feeds yes\nprepopulate-query-feeds yes\nconfirm-exit no\nreload-threads 2\nfeedlist-format "%t %v"\n'
                with reader(root,cfg,urls) as (file,screen,send,wait):
                    wait(lambda s:'New 2' in s and 'All 2' in s)
                    phase=1;send('R')
                    wait(lambda s:slow_started.is_set() and 'New 3' in s and 'All 3' in s,3)
                    self.assertFalse(release.is_set())
                    release.set();wait(lambda s:'New 4' in s and 'All 4' in s)
        finally:release.set();server.shutdown();server.server_close();thread.join()
