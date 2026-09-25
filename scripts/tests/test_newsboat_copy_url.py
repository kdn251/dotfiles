import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('copy_url', SCRIPTS/'newsboat-copy-url.py')
copy=importlib.util.module_from_spec(spec);spec.loader.exec_module(copy)

class CopyTests(unittest.TestCase):
    def test_copies_exact_url_without_shell_interpretation(self):
        url='https://example.org/article?q=a&other=$(literal)#section'
        with patch.object(copy.subprocess,'run') as run:
            copy.copy_url(url)
            self.assertEqual(run.call_args.kwargs['input'],url.encode())
            self.assertNotIn('shell',run.call_args.kwargs)
            self.assertEqual(run.call_args.args[0][0],'wl-copy')

    def test_rejects_non_web_placeholders(self):
        with patch.object(copy.subprocess,'run') as run:
            for url in ['', 'newsboat-vods://empty', 'file:///tmp/file', 'https://example.org\nmore']:
                with self.assertRaises(ValueError):copy.copy_url(url)
            run.assert_not_called()

    def test_ctrl_c_copies_selected_article_and_video_without_quitting(self):
        import os,sys,pty,fcntl,termios,struct,select,signal,time,tempfile,sqlite3
        import pyte
        binary=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'scripts').symlink_to(SCRIPTS);bin=root/'bin';bin.mkdir();clipboard=root/'clipboard'
            command=bin/'wl-copy';command.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nPath('+repr(str(clipboard))+').write_bytes(sys.stdin.buffer.read())\n');command.chmod(0o755)
            article='https://example.org/article?q=one&next=two#section';video='https://www.youtube.com/watch?v=abcdefghijk'
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Copy test</title><link>https://example.org</link><description>Test</description><item><title>Article one</title><link>'+article.replace('&','&amp;')+'</link><guid>one</guid><description>Body one</description></item><item><title>Video two</title><link>'+video+'</link><guid>two</guid><description>Body two</description></item></channel></rss>')
            urls=root/'urls';urls.write_text(feed.as_uri()+'\n')
            binding=next(line for line in (SCRIPTS.parents[1]/'newsboat/.newsboat/config').read_text().splitlines() if line.startswith('bind ^C '))
            config=root/'config';config.write_text('confirm-exit no\narticle-sort-order title-asc\nbind-key j down\n'+binding+'\n')
            cache=root/'cache.db';args=[str(binary),'-q','-C',str(config),'-u',str(urls),'-c',str(cache)]
            env=dict(os.environ,HOME=str(root),PATH=str(bin)+':'+os.environ['PATH'],TERM='xterm-256color')
            subprocess=copy.subprocess
            subprocess.run(args+['-x','reload'],env=env,check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(env);os.execv(str(binary),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,110,0,0));screen=pyte.Screen(110,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.05)[0]:
                        try:stream.feed(os.read(fd,65536))
                        except OSError:break
                    if predicate('\n'.join(screen.display)):return
                self.fail('\n'.join(screen.display))
            try:
                wait(lambda s:'Copy test' in s);time.sleep(.3);os.write(fd,b'\r')
                wait(lambda s:'Article one' in s and 'Video two' in s and screen.cursor.y==1)
                os.write(fd,b'\x03');wait(lambda s:clipboard.exists())
                self.assertEqual(clipboard.read_text(),article)
                with sqlite3.connect(cache) as db:
                    self.assertEqual(db.execute('SELECT unread FROM rss_item WHERE guid="one"').fetchone()[0],1)
                clipboard.unlink();os.write(fd,b'j');wait(lambda s:screen.cursor.y==2)
                os.write(fd,b'\x03');wait(lambda s:clipboard.exists())
                self.assertEqual(clipboard.read_text(),video)
                clipboard.unlink();os.write(fd,b'\r');wait(lambda s:'Body two' in s)
                os.write(fd,b'\x03');wait(lambda s:clipboard.exists())
                self.assertEqual(clipboard.read_text(),video)
                self.assertEqual(os.waitpid(pid,os.WNOHANG)[0],0)
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

    def test_mpv_ctrl_c_copies_original_url_during_local_playback(self):
        import os,socket,json,time,tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bin=root/'bin';bin.mkdir();clipboard=root/'clipboard';ipc=root/'mpv.sock'
            command=bin/'wl-copy';command.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\nPath('+repr(str(clipboard))+').write_bytes(sys.stdin.buffer.read())\n');command.chmod(0o755)
            sample=root/'local.wav'
            copy.subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','anullsrc','-t','1',str(sample)],check=True)
            url='https://www.youtube.com/watch?v=abcdefghijk&t=42'
            env=dict(os.environ,PATH=str(bin)+':'+os.environ['PATH'],NEWSBOAT_MEDIA_URL=url)
            process=copy.subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--keep-open=yes',
                '--input-ipc-server='+str(ipc),'--script='+str(SCRIPTS/'newsboat-copy-url.lua'),str(sample)],
                env=env,stdout=copy.subprocess.DEVNULL,stderr=copy.subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+5
                while not ipc.exists() and time.monotonic()<deadline:time.sleep(.02)
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.connect(str(ipc))
                    # A real key event exercises the override of mpv's built-in quit binding.
                    sock.sendall(json.dumps({'command':['keypress','Ctrl+c']}).encode()+b'\n')
                    deadline=time.monotonic()+5
                    while not clipboard.exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertEqual(clipboard.read_text(),url)
                    self.assertIsNone(process.poll(),'Ctrl+C must not quit mpv')
                    clipboard.unlink()
                    sock.sendall(json.dumps({'command':['loadfile',str(sample),'replace']}).encode()+b'\n')
                    time.sleep(.15)
                    sock.sendall(json.dumps({'command':['keypress','Ctrl+c']}).encode()+b'\n')
                    deadline=time.monotonic()+5
                    while not clipboard.exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertEqual(clipboard.read_text(),url)
                    self.assertIsNone(process.poll())
            finally:
                if process.poll() is None:process.terminate()
                process.wait(timeout=5)
