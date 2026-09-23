"""Read downloads remain searchable with hide-read enabled."""
import unittest
import sqlite3
import os,pty,fcntl,termios,struct,tempfile,subprocess,time,select,json
from pathlib import Path
try:
 import pyte
except ImportError:
 pyte=None
b=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',str(Path.home()/'.local/lib/newsboat-paged/newsboat')))

@unittest.skipUnless(pyte and b.exists(), "requires custom Newsboat and pyte")
class DownloadSearchTests(unittest.TestCase):
 def test_read_download_search(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); f=r/'feed';f.write_text('<rss version="2.0"><channel><title>Source</title><item><title>Needle video</title><guid>one</guid></item></channel></rss>')
   (r/'urls').write_text(json.dumps('query:📥 Downloads:title =~ "Needle"',ensure_ascii=False)+'\n'+f.as_uri()+'\n')
   (r/'config').write_text('show-read-articles no\nprepopulate-query-feeds yes\n')
   args=[str(b),'-C',str(r/'config'),'-u',str(r/'urls'),'-c',str(r/'cache')]
   subprocess.run(args+['-x','reload'],capture_output=True,check=True)
   with sqlite3.connect(r/'cache') as db:db.execute('UPDATE rss_item SET unread=0')
   pid,fd=pty.fork()
   if pid==0:
    os.environ['TERM']='xterm-256color';os.execv(str(b),args)
   fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0));s=pyte.Screen(100,24);st=pyte.ByteStream(s)
   def drain():
    end=time.monotonic()+.7
    while time.monotonic()<end:
     if select.select([fd],[],[],.05)[0]:st.feed(os.read(fd,65536))
   try:
    drain();os.write(fd,b'\n');drain();assert any('Needle video' in x for x in s.display[1:]), 'Read download hidden';os.write(fd,b'/Needle\n');drain();assert 'Search results' in s.display[0];assert any('Needle video' in x for x in s.display[1:]), 'Read search match hidden'
   finally:
    os.kill(pid,15);os.waitpid(pid,0);os.close(fd)
