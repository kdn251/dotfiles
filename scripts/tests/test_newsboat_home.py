"""Native All-folder navigation without launching a second Newsboat instance."""
import fcntl,json,os,pty,select,signal,sqlite3,struct,subprocess,tempfile,termios,time,unittest
from pathlib import Path
try:
 import pyte
except ImportError:
 pyte=None
BINARY=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.local/lib/newsboat-paged/newsboat'))
CONFIG=Path(__file__).resolve().parents[2]/'newsboat/.newsboat/config'

@unittest.skipUnless(pyte and BINARY.exists(),'requires pyte and custom Newsboat')
class HomeTests(unittest.TestCase):
 def test_home_views_all_sources_and_back(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);config=root/'config';urls=root/'urls'
   selected=[line for line in CONFIG.read_text().splitlines() if line.startswith(('run-on-startup ','feedlist-title-format ','show-read-feeds ','confirm-exit ','bind n '))]
   config.write_text('\n'.join(selected)+'\nprepopulate-query-feeds yes\nfeedlist-format "%t | %v %k"\nbind-key j down\nbind-key k up\n')
   lines=[json.dumps('query:'+name+':link = "none"',ensure_ascii=False) for name in ['📬 New','⭐ Starred','📥 Downloads','📣 Commentary','🌎 All']]
   for name in ['Source A','Source B']:
    feed=root/(name.replace(' ','')+'.xml');feed.write_text(f'<rss version="2.0"><channel><title>{name}</title><link>https://example.com</link><description>Test</description><item><title>Article {name}</title><link>https://example.com/{name[-1]}</link><guid>{name}</guid></item></channel></rss>');lines.append(feed.as_uri())
   urls.write_text('\n'.join(lines)+'\n');args=[str(BINARY),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache')]
   subprocess.run(args+['-x','reload'],check=True,capture_output=True)
   with sqlite3.connect(root/'cache') as db:db.execute("UPDATE rss_item SET unread=0 WHERE title='Article Source B'")
   (root/'stars.count').write_text('3\n')
   (root/'stars.commentary.count').write_text('2\n')
   pid,fd=pty.fork()
   if not pid:
    os.environ.update(NEWSBOAT_STARRED_STATUS=str(root/'stars'),HOME=directory,TERM='xterm-256color',NEWSBOAT_LIVE_QUERIES=str(urls));os.execv(str(BINARY),args)
   fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0));screen=pyte.Screen(100,24);stream=pyte.ByteStream(screen)
   def wait(predicate):
    end=time.monotonic()+7
    while time.monotonic()<end:
     if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
     if predicate('\n'.join(screen.display)):return
    self.fail('\n'.join(screen.display))
   try:
    wait(lambda s:'🚢 Newsboat' in s and s.count(' unread')==2)
    self.assertIn('🌎 All | 1 unread', '\n'.join(screen.display))
    self.assertIn('⭐ Starred | 3 items','\n'.join(screen.display))
    self.assertIn('📣 Commentary | 2 items','\n'.join(screen.display))
    os.write(fd,b'l');wait(lambda s:'⭐ Starred | 3 items' in screen.display[1])
    self.assertIn('🌎 All | 1 unread','\n'.join(screen.display))
    os.write(fd,b'l');wait(lambda s:'📬 New' in screen.display[1])
    os.write(fd,b':5\n\n');wait(lambda s:s.startswith(' 🌎 All') and s.count(' unread')==2)
    self.assertIn('Source B | 0 unread','\n'.join(screen.display))
    self.assertNotIn('📬 New','\n'.join(screen.display))
    urls.write_text(urls.read_text()+'\n')
    os.write(fd,b'\n');wait(lambda s:"Articles in feed 'Source A'" in s)
    os.write(fd,b'n');wait(lambda s:'Articles in feed' in s)
    os.write(fd,b'q');wait(lambda s:s.startswith(' 🌎 All') and s.count(' unread')==2)
    os.write(fd,b'q');wait(lambda s:'🚢 Newsboat' in s and s.count(' unread')==2)
    self.assertEqual(screen.cursor.y,5)
    self.assertIn('🌎 All | 0 unread', '\n'.join(screen.display))
    os.write(fd,b'q');wait(lambda s:'Do you really want to quit' in s)
    os.write(fd,b'n')
   finally:
    os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
