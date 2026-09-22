"""Starring must preserve the page even when read rows remain visible."""
import os,pty,fcntl,termios,struct,select,time,tempfile,subprocess,signal,re,unittest
from pathlib import Path
try:
 import pyte
except ImportError:
 pyte=None
binary=os.environ.get('NEWSBOAT_PAGED_BINARY',str(Path.home()/'.local/lib/newsboat-paged/newsboat'))

@unittest.skipUnless(pyte and Path(binary).exists(), 'requires pyte and local Newsboat build')
class StarPositionTests(unittest.TestCase):
 def test_starring_does_not_refilter_or_move_page(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);feed=r/'feed.xml';url=r/'urls';stars=r/'stars';helper=r/'star.py'
   feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description>'+''.join(f'<item><title>Video {i:03}</title><link>https://example.com/{i}</link><guid>{i}</guid></item>' for i in range(1,101))+'</channel></rss>')
   url.write_text('"query:New:unread = \\"yes\\""\n'+feed.as_uri()+'\n')
   helper.write_text('import os,sys\nfrom pathlib import Path\nPath(os.environ["NEWSBOAT_STARRED_STATUS"]).write_text(sys.argv[1]+"\\n")\n')
   cfg=r/'config';cfg.write_text('show-read-feeds yes\nshow-read-articles no\narticle-sort-order title-asc\nprepopulate-query-feeds yes\narticlelist-format "%-9p %t"\nbind-key j down\nbind-key k up\nconfirm-exit no\n'+f'bind s articlelist set browser "python3 {helper} %u" ; open-in-browser-noninteractively ; set browser "true" ; toggle-article-read "read" "stay"\n')
   args=[binary,'-q','-C',str(cfg),'-u',str(url),'-c',str(r/'cache')];subprocess.run(args+['-x','reload'],check=True,capture_output=True)
   pid,fd=pty.fork()
   if not pid:
    os.environ.update(HOME=d,TERM='xterm-256color',NEWSBOAT_PAGE_SCROLL='1',NEWSBOAT_STARRED_STATUS=str(stars),NEWSBOAT_DOWNLOAD_STATUS=str(r/'status'),NEWSBOAT_LIVE_QUERIES=str(url));os.execv(binary,args)
   fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0));screen=pyte.Screen(100,24);stream=pyte.ByteStream(screen)
   def pump(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
     if select.select([fd],[],[],.02)[0]:stream.feed(os.read(fd,65536))
   def snapshot():return screen.cursor.y,[(y,re.search(r'Video \d+',s).group()) for y,s in enumerate(screen.display) if re.search(r'Video \d+',s)]
   try:
    pump(.3);os.write(fd,b'\n');pump(.3);os.write(fd,b'j'*25);pump(.3);os.write(fd,b'N');pump(.3);os.write(fd,b'j'*5);pump(.3);before=snapshot();self.assertTrue(before[1]);os.write(fd,b's');pump(1.5);after=snapshot();self.assertEqual(before,after);self.assertIn("󰓎", "\n".join(screen.display))
    selected=dict(before[1])[before[0]]
    os.write(fd,b"q\n");pump(.6)
    self.assertNotIn(selected,"\n".join(screen.display))
   finally:os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
