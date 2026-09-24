import os,pathlib,tempfile,subprocess,pty,fcntl,termios,struct,time,select,signal,pyte
import unittest

class FavoritesUndoUITests(unittest.TestCase):
 def test_save_remove_and_cross_view_undo(self):
  repo=pathlib.Path(__file__).resolve().parents[2];scripts=repo/'scripts/scripts';binary=pathlib.Path(os.environ.get('NEWSBOAT_PAGED_BINARY',pathlib.Path.home()/'.local/lib/newsboat-paged/newsboat'))
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);home=root/'.newsboat';home.mkdir();(root/'scripts').symlink_to(scripts)
   b=root/'.local/lib/newsboat-paged';b.mkdir(parents=True);(b/'newsboat').symlink_to(binary)
   feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description><item><title>Favorites test article</title><link>https://www.youtube.com/watch?v=favoriteTest</link><guid>1</guid><description>Saved text</description></item></channel></rss>')
   cfg='\n'.join(l for l in (repo/'newsboat/.newsboat/config').read_text().splitlines() if not l.startswith(('include ','urls-source ','miniflux-')))+'\nurls-source local\n'
   (home/'config').write_text(cfg);(home/'urls').write_text('"query:📬 New:unread = \\"yes\\""\n"query:🌎 All:link = \\"none\\""\n'+feed.as_uri()+'\n')
   env=dict(os.environ,HOME=d,XDG_STATE_HOME=str(root/'state'),NEWSBOAT_CACHE=str(home/'cache.db'),NEWSBOAT_URLS_FILE=str(home/'urls'))
   subprocess.run([str(binary),'-C',str(home/'config'),'-u',str(home/'urls'),'-c',str(home/'cache.db'),'-x','reload'],env=env,check=True,capture_output=True)
   subprocess.run(['python',str(scripts/'newsboat-favorites.py'),'rebuild'],env=env,check=True)
   pid,fd=pty.fork()
   if pid==0:
    os.environ.update(env,TERM='xterm-256color');os.execv('/usr/bin/python',['python',str(scripts/'newsboat-session.py')])
   fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,110,0,0));screen=pyte.Screen(110,24);stream=pyte.ByteStream(screen)
   def wait(check):
    end=time.monotonic()+8
    while time.monotonic()<end:
     if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
     if check('\n'.join(screen.display)):return
    raise AssertionError('\n'.join(screen.display))
   try:
    wait(lambda s:'  Favorites' in s and '🚢 Newsboat' in s)
    os.write(fd,b'\n');wait(lambda s:'Favorites test article' in s)
    os.write(fd,b'R');wait(lambda s:'feeds refreshed' in s)
    wait(lambda s:'feeds refreshed' not in s)
    os.write(fd,b'f');wait(lambda s:'' in screen.display[1])
    os.write(fd,b'U');wait(lambda s:'' not in screen.display[1] and 'Undid last Favorites' in s)
    os.write(fd,b'f');wait(lambda s:'' in screen.display[1])
    os.write(fd,b'q');wait(lambda s:'🚢 Newsboat' in s)
    self.assertNotIn('', next(row for row in screen.display if 'Favorites' in row))
    os.write(fd,b':2\n\n');wait(lambda s:'Favorites test article' in s)
    self.assertTrue(screen.display[0].startswith('   Favorites'), screen.display[0])
    self.assertIn('', screen.display[0])
    self.assertEqual(screen.buffer[0][screen.display[0].index('')].fg, 'red')
    os.write(fd,b'R');wait(lambda s:'feeds refreshed' in s)
    wait(lambda s:'feeds refreshed' not in s)
    os.write(fd,b'F');wait(lambda s:'Favorites test article' not in s)
    os.write(fd,b'U');wait(lambda s:'Favorites test article' in s and '' in screen.display[1])
    os.write(fd,b'F');wait(lambda s:'Favorites test article' not in s)
    os.write(fd,b'q');wait(lambda s:'🚢 Newsboat' in s and '  Favorites' in s)
    assert screen.cursor.y==2,screen.cursor.y
    heart_column = screen.display[2].index('')
    self.assertEqual(screen.buffer[2][heart_column].bg, screen.buffer[2][heart_column + 2].bg)
    os.write(fd,b'U');wait(lambda s:'Undid last Favorites' in s)
    os.write(fd,b'\n');wait(lambda s:'Favorites test article' in s)
    os.write(fd,b'q');wait(lambda s:'🚢 Newsboat' in s)
   finally:
    def stop_tree(parent):
     try: children=pathlib.Path(f'/proc/{parent}/task/{parent}/children').read_text().split()
     except OSError: children=[]
     for child in children: stop_tree(int(child))
     try: os.kill(parent,signal.SIGTERM)
     except ProcessLookupError: pass
    stop_tree(pid);os.waitpid(pid,0);os.close(fd)
