"""Home navigation through native All/article views and nested overlays."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
import pyte

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

class HomeTests(unittest.TestCase):
    def test_home_from_all_articles_help_and_nested_playlist(self):
        binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
        if not binary.exists():self.skipTest('custom Newsboat required')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);wrapper=root/'newsboat-session.py';shutil.copyfile(SCRIPTS/'newsboat-session.py',wrapper)
            bindir=root/'.local/lib/newsboat-paged';bindir.mkdir(parents=True);(bindir/'newsboat').symlink_to(binary)
            rss=root/'feed.xml';rss.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description><item><title>Episode</title><guid>episode</guid><link>https://www.youtube.com/watch?v=abc123DEF45</link></item></channel></rss>')
            config=root/'config';urls=root/'urls';cache=root/'cache'
            config.write_text('show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nfeedlist-title-format "HOMESCREEN"\narticlelist-title-format "EPISODES"\nbind h everywhere set browser "newsboat-home://show"\nbind t everywhere set browser "newsboat-starred://show"\nrun-on-startup set-filter '+json.dumps('rssurl =~ "^query:"')+'\n')
            urls.write_text(json.dumps('query:🌎 All:title =~ "Episode"',ensure_ascii=False)+'\n'+rss.as_uri()+'\n')
            args=['-C',str(config),'-u',str(urls),'-c',str(cache)]
            subprocess.run([str(binary),*args,'-x','reload'],check=True,capture_output=True)
            # Saved view runs a real native article list, including its h binding.
            request_helper=root/'request.py'
            request_helper.write_text('import os\nfrom pathlib import Path\nPath(os.environ["NEWSBOAT_PLAYLIST_REQUEST"]).write_text("https://www.youtube.com/watch?v=abc123DEF45")\n')
            nested=root/'nested-config';nested.write_text(config.read_text().split('run-on-startup')[0]+'articlelist-title-format "NESTED"\nrun-on-startup open\nbind P everywhere set browser "python3 '+str(request_helper)+' %u" ; open-in-browser-noninteractively\n')
            # Use a real native home request for the saved view, and a simple
            # overlay for testing that both nested PTYs close on the same request.
            (root/'newsboat-starred.py').write_text('import os,subprocess\nfrom pathlib import Path\n'+
                'cmd='+repr([str(binary),'-C',str(nested),'-u',str(root/'nested-urls'),'-c',str(root/'nested-cache')])+'\n'+
                'subprocess.run(cmd+["-x","reload"],capture_output=True,check=True)\nsubprocess.call(cmd)\n')
            (root/'nested-urls').write_text(rss.as_uri()+'\n')
            (root/'newsboat-playlists.py').write_text('import os,tty\nfrom pathlib import Path\ntty.setraw(0)\nos.write(1,b"\\x1b[H\\x1b[2JPLAYLIST")\nwhile True:\n key=os.read(0,1)\n if key==b"h":Path(os.environ["NEWSBOAT_HOME_REQUEST"]).write_text("home")\n')
            env=dict(os.environ,HOME=directory,TERM='xterm-256color',XDG_STATE_HOME=str(root/'state'))
            pid,fd=pty.fork()
            if pid==0:os.execve(sys.executable,[sys.executable,str(wrapper),*args],env)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,0,0))
            screen=pyte.Screen(120,24);stream=pyte.ByteStream(screen)
            def until(text):
                end=time.monotonic()+6
                while time.monotonic()<end:
                    if select.select([fd],[],[],.05)[0]:
                        try:stream.feed(os.read(fd,65536))
                        except OSError:break
                    if text in '\n'.join(screen.display):return
                self.fail('\n'.join(screen.display))
            def press(keys,text):
                os.write(fd,keys);until(text)
            try:
                until('HOMESCREEN')
                press(b'\n','🌎 All')
                press(b'\n','EPISODES')
                press(b'h','HOMESCREEN')
                press(b'h','HOMESCREEN')  # Home on the homepage must not quit.
                press(b'?','Help')
                press(b'h','HOMESCREEN')
                press(b't','NESTED')
                press(b'h','HOMESCREEN')
                press(b't','NESTED')
                # Find only this wrapper's request path from its inherited child env.
                os.write(fd,b'P')
                until('PLAYLIST')
                press(b'h','HOMESCREEN')
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
