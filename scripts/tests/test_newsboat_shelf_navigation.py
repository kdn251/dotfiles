import os,pty,tempfile,select,time,signal,subprocess,sqlite3
import unittest
import shutil
from pathlib import Path
scripts=Path(__file__).resolve().parents[1]/'scripts'

@unittest.skipUnless(shutil.which('newsboat'), 'requires Newsboat')
class ShelfNavigationTests(unittest.TestCase):
 def test_main_entry_unshelf_and_empty_reopen(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'.newsboat').mkdir();config=p/'.newsboat/config'
   config.write_text('bind-key j down\nprepopulate-query-feeds yes\nfeedlist-format "%t | %U unread"\nshow-read-feeds yes\nrun-on-startup set-filter "unread_count > 0 or feedtitle = \\"Shelf\\""\n')
   with config.open('a') as output:
    output.write(f'bind S articlelist set browser "python3 {scripts}/newsboat-shelf.py consume %u" ; open-in-browser-noninteractively\n')
   (p/'urls').write_text('"query:Shelf:link = \\"newsboat-shelf://navigation\\""\n')
   feed = p/'feed.xml'
   feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description><item><title>saved-article</title><link>https://example.com/saved-article</link><guid>one</guid></item></channel></rss>')
   with (p/'urls').open('a') as output: output.write(feed.as_uri()+'\n')
   env=dict(os.environ,HOME=tmp,XDG_STATE_HOME=str(p/'state'),TERM='xterm-256color', NEWSBOAT_URLS_FILE=str(p/'urls'))
   subprocess.run(['newsboat', '-q', '-C', str(config), '-u', str(p/'urls'), '-c', str(p/'main-cache'), '-x', 'reload'], env=env, check=True, capture_output=True)
   subprocess.run(['python3', '-c', "import runpy,sys; runpy.run_path(sys.argv[1])['save']('https://example.com/saved-article')", str(scripts/'newsboat-shelf.py')], env=env, check=True)
   db=p/'state/newsboat/shelf.db'
   def count():
    c=sqlite3.connect(db)
    try:return c.execute('select count(*) from shelf').fetchone()[0]
    finally:c.close()
   pid,fd=pty.fork()
   if not pid:os.execvpe('python3',['python3',str(scripts/'newsboat-session.py'),'-C',str(config),'-u',str(p/'urls'),'-c',str(p/'main-cache')],env)
   data=bytearray()
   def until(predicate):
    end=time.monotonic()+7
    while time.monotonic()<end:
     if predicate():return
     if select.select([fd],[],[],.05)[0]:data.extend(os.read(fd,65536))
    raise AssertionError(repr(data[-1200:]))
   try:
    until(lambda:b'Shelf | 1 unread' in data);data.clear();os.write(fd,b'\n')
    until(lambda:b'saved-article' in data);assert b'Shelf' in data;assert count()==1
    os.write(fd,b'S');until(lambda:count()==0);time.sleep(.1);data.clear();os.write(fd,b'q');until(lambda:b'Shelf | 0 unread' in data)
    time.sleep(.3)
    data.clear();os.write(fd,b'\n');until(lambda:b"Articles in feed 'Source'" in data)
    os.write(fd,b'q');time.sleep(.1)
    data.clear();os.write(fd,b':1\n\n');until(lambda:b'Shelf is empty' in data)
    data.clear();os.write(fd,b'q');until(lambda:b'Shelf | 0 unread' in data)
    time.sleep(.2)
    data.clear();os.write(fd,b'\n');until(lambda:b"Articles in feed 'Source'" in data)
    subprocess.run(['python3', '-c', "import runpy,sys; runpy.run_path(sys.argv[1])['save']('https://example.com/saved-article')", str(scripts/'newsboat-shelf.py')], env=env, check=True)
    data.clear();os.write(fd,b'q');until(lambda:b'Shelf | 1 unread' in data)
    time.sleep(.2)
    data.clear();os.write(fd,b'\n');until(lambda:b"Articles in feed 'Source'" in data)
    self.assertNotIn(b"Articles in feed 'Shelf'", data)
    os.write(fd,b'S');until(lambda:count()==0)
    data.clear();os.write(fd,b'q');until(lambda:b'Shelf | 0 unread' in data)
    time.sleep(.2)
    data.clear();os.write(fd,b'\n');until(lambda:b"Articles in feed 'Source'" in data)
    self.assertNotIn(b"Articles in feed 'Shelf'", data)
    # Return from Shelf itself to the previously opened source, not Shelf.
    subprocess.run(['python3', '-c', "import runpy,sys; runpy.run_path(sys.argv[1])['save']('https://example.com/saved-article')", str(scripts/'newsboat-shelf.py')], env=env, check=True)
    data.clear();os.write(fd,b'q');until(lambda:b'Shelf | 1 unread' in data)
    time.sleep(.2)
    data.clear();os.write(fd,b':1\n\n');until(lambda:b"Articles in feed 'Shelf'" in data)
    os.write(fd,b'S');until(lambda:count()==0)
    data.clear();os.write(fd,b'q');until(lambda:b'Shelf | 0 unread' in data)
    time.sleep(.2)
    data.clear();os.write(fd,b'\n');until(lambda:b"Articles in feed 'Source'" in data)
    self.assertNotIn(b"Articles in feed 'Shelf'", data)
   finally:os.killpg(pid,signal.SIGKILL);os.waitpid(pid,0);os.close(fd)
