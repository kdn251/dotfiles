import http.server,json,os,pty,tempfile,select,time,signal,subprocess,threading
import unittest,shutil,fcntl,struct,termios
from pathlib import Path
try:
 import pyte
except ImportError:
 pyte=None
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

@unittest.skipUnless(shutil.which('newsboat'),'requires Newsboat')
class NavigationTests(unittest.TestCase):
 def test_native_starred_entry(self):
  binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
  if not binary.exists():self.skipTest('requires native build')
  self.exercise_navigation(binary)

 def test_reading_keeps_star_and_explicit_unstar_removes_it(self):
  self.exercise_navigation()

 def exercise_navigation(self, binary=None):
  row=dict(id=1,url='https://example.com/saved',title='saved-article',content='Full article body',feed={'title':'Source'},starred=True,status='read')
  class Handler(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    data={'total':int(row['starred']),'entries':[row] if row['starred'] else []} if self.path.startswith('/v1/entries?') else row
    self.send_response(200);self.end_headers();self.wfile.write(json.dumps(data).encode())
   def do_PUT(self):
    data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));row['starred']=data['starred']
    self.send_response(204);self.end_headers()
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);(p/'.newsboat').mkdir();(p/'scripts').symlink_to(SCRIPTS,target_is_directory=True)
    if binary:
     target=p/'.local/lib/newsboat-paged/newsboat';target.parent.mkdir(parents=True);target.symlink_to(binary)
    creds=p/'creds';creds.write_text(f'miniflux-url "http://127.0.0.1:{server.server_port}"\nminiflux-login test\nminiflux-password test\n')
    config=p/'.newsboat/config';config.write_text('prepopulate-query-feeds yes\nshow-read-feeds yes\narticlelist-title-format "%T"\nfeedlist-format "%t | %U unread"\nrun-on-startup set-filter "unread_count > 0 or feedtitle = \\"⭐ Starred\\""\n')
    urls=p/'urls';urls.write_text('"query:⭐ Starred:link = \\"https://example.com/saved\\""\n')
    feed=p/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description><item><title>saved-article</title><link>https://example.com/saved</link><guid>1</guid></item></channel></rss>')
    with urls.open('a') as out:out.write(feed.as_uri()+'\n')
    env=dict(os.environ,HOME=tmp,TERM='xterm-256color',NEWSBOAT_URLS_FILE=str(urls),NEWSBOAT_CACHE=str(p/'cache'),NEWSBOAT_MINIFLUX_CONFIG=str(creds),XDG_STATE_HOME=str(p/'state'))
    args=['-C',str(config),'-u',str(urls),'-c',str(p/'cache')]
    subprocess.run(['newsboat','-q',*args,'-x','reload'],env=env,check=True,capture_output=True)
    pid,fd=pty.fork()
    if not pid:os.execvpe('python3',['python3',str(SCRIPTS/'newsboat-session.py'),*args],env)
    fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',30,120,0,0));data=bytearray()
    screen=pyte.Screen(120,30) if pyte else None
    stream=pyte.ByteStream(screen) if screen else None
    def until(predicate):
     end=time.monotonic()+8
     while time.monotonic()<end:
      if predicate():return
      if select.select([fd],[],[],.05)[0]:
       chunk=os.read(fd,65536);data.extend(chunk)
       if stream:stream.feed(chunk)
     raise AssertionError(repr(data[-1800:]))
    try:
     until(lambda:b'Starred | 1 unread' in data);data.clear();os.write(fd,b'\n')
     until(lambda:b'saved-article' in data);self.assertTrue(row['starred'])
     if binary:
      self.assertIn(b'\x1b[?2026h',data)
      self.assertNotIn(b'Updating query feed',data)
     data.clear();os.write(fd,b'\n');until(lambda:b'Full article body' in data)
     data.clear();os.write(fd,b'q');until(lambda:b'saved-article' in data);self.assertTrue(row['starred'])
     os.write(fd,b'S');until(lambda:not row['starred']);time.sleep(.2)
     if binary and screen:until(lambda:'saved-article' not in '\n'.join(screen.display))
     data.clear();os.write(fd,b'q');until(lambda:b'Starred | 0 unread' in data)
     self.assertNotIn(b'\x1b[?1049l',data)
     self.assertNotIn(b'\x1b[?1049h',data)
     time.sleep(.2);data.clear();os.write(fd,b'\n')
     until(lambda:b'No starred items' in data)
     data.clear();os.write(fd,b'q');until(lambda:b'Starred | 0 unread' in data)
     self.assertNotIn(b'\x1b[?1049l',data)
     self.assertNotIn(b'\x1b[?1049h',data)
    finally:
     os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
  finally:server.shutdown();server.server_close();thread.join()
