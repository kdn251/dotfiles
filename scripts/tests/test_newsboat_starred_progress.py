import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('opener',SCRIPTS/'newsboat-open.py')
opener=importlib.util.module_from_spec(spec);spec.loader.exec_module(opener)

class StarredProgressTests(unittest.TestCase):
    def test_starred_article_registers_original_without_downloading(self):
        url='https://example.org/article'
        with patch.dict(os.environ,NEWSBOAT_STARRED_VIEW='1'),patch('newsboat_articles.find',return_value=None),patch('newsboat_browser_reading.register') as register,patch.object(opener.os,'execv') as execute:
            opener.open_url(url)
            register.assert_called_once_with(url)
            self.assertEqual(execute.call_args.args[1][-1],url)
        with patch.dict(os.environ,NEWSBOAT_STARRED_VIEW='1'),patch('newsboat_articles.find',return_value=Path('/tmp/article.html')),patch('newsboat_reading.reader_url',return_value='http://127.0.0.1/reader') as reader,patch('newsboat_browser_reading.register') as register,patch.object(opener.os,'execv') as execute:
            opener.open_url(url)
            register.assert_not_called()
            reader.assert_called_once_with(url)
            self.assertEqual(execute.call_args.args[1][-1],'http://127.0.0.1/reader')

    def test_video_does_not_register_as_article(self):
        with patch.dict(os.environ,NEWSBOAT_STARRED_VIEW='1'),patch('newsboat_browser_reading.register') as register,patch.object(opener.os,'execv') as execute:
            opener.open_url('https://www.youtube.com/watch?v=abcdefghijk')
            register.assert_not_called()
            self.assertTrue(execute.call_args.args[0].endswith('newsboat-play-video.sh'))

    def test_real_mpv_resumes_and_does_not_rewind_on_second_load(self):
        import socket,json,time
        import newsboat_watch_progress as progress
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state/newsboat';sample=root/'local.wav';ipc=root/'mpv.sock'
            url='https://www.youtube.com/watch?v=abc123DEF45'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','anullsrc','-t','20',str(sample)],check=True)
            with patch.object(progress,'STATE',state),patch.object(progress.media,'STATE',state/'downloads'),patch.dict(os.environ,NEWSBOAT_CACHE=str(root/'none')):
                progress.record(url,8,20)
            env=dict(os.environ,XDG_STATE_HOME=str(root/'state'),NEWSBOAT_MEDIA_URL=url,NEWSBOAT_MAINTENANCE=str(SCRIPTS/'newsboat-maintenance.py'),NEWSBOAT_CACHE=str(root/'none'))
            process=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--pause=yes','--keep-open=yes',
                '--input-ipc-server='+str(ipc),'--script='+str(SCRIPTS/'newsboat-watch-completion.lua'),str(sample)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                end=time.monotonic()+5
                while not ipc.exists() and time.monotonic()<end:time.sleep(.02)
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.settimeout(3);sock.connect(str(ipc));stream=sock.makefile('rb');ident=0
                    def cmd(args):
                        nonlocal ident
                        ident+=1;sock.sendall(json.dumps(dict(command=args,request_id=ident)).encode()+b'\n')
                        while True:
                            result=json.loads(stream.readline())
                            if result.get('request_id')==ident:return result.get('data')
                    end=time.monotonic()+5
                    while time.monotonic()<end:
                        position=cmd(['get_property','time-pos'])
                        if position is not None and position>=7.9:break
                        time.sleep(.05)
                    self.assertAlmostEqual(position,8,delta=.2)
                    cmd(['loadfile',str(sample),'replace','0','start=12'])
                    end=time.monotonic()+3
                    while time.monotonic()<end:
                        position=cmd(['get_property','time-pos'])
                        if position is not None and position>=11.9:break
                        time.sleep(.05)
                    self.assertAlmostEqual(position,12,delta=.2)
                    stream.close()
            finally:
                process.terminate();process.wait(timeout=5)
            with patch.object(progress,'STATE',state):
                self.assertAlmostEqual(progress.resume_position(url,20),12,delta=.2)

    def test_starred_rows_show_live_video_and_article_progress(self):
        import pty,fcntl,termios,struct,select,signal,time
        import pyte
        binary=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=root/'status';status.write_text('')
            Path(str(status)+'.watched').write_text('https://www.youtube.com/watch?v=abc123DEF45\t42%\n')
            read=Path(str(status)+'.read');read.write_text('https://example.org/article\t72%\n')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>⭐ Starred</title><link>https://example.org</link><description>Test</description><item><title>Article</title><link>https://example.org/article</link><guid>a</guid><description>Body</description></item><item><title>Video</title><link>https://www.youtube.com/watch?v=abc123DEF45</link><guid>b</guid></item></channel></rss>')
            urls=root/'urls';urls.write_text(feed.as_uri()+'\n');config=root/'config';config.write_text('confirm-exit no\narticle-sort-order title-asc\n')
            args=[str(binary),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache.db')]
            env=dict(os.environ,TERM='xterm-256color',NEWSBOAT_DOWNLOAD_STATUS=str(status))
            subprocess.run(args+['-x','reload'],check=True,env=env,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:os.environ.update(env);os.execv(str(binary),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,110,0,0));screen=pyte.Screen(110,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                end=time.monotonic()+5
                while time.monotonic()<end:
                    if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
                    if predicate('\n'.join(screen.display)):return
                self.fail('\n'.join(screen.display))
            try:
                wait(lambda text:'Starred' in text);time.sleep(.3);os.write(fd,b'\r')
                wait(lambda text:'72%' in text and '42%' in text and screen.cursor.y==1)
                self.assertIn('72%',next(line for line in screen.display[1:] if 'Article' in line))
                self.assertIn('42%',next(line for line in screen.display if 'Video' in line))
                read.write_text('https://example.org/article\t81%\n')
                wait(lambda text:'81%' in text and screen.cursor.y==1)
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

    def test_starred_progress_order_newest_ties_and_stable_selection(self):
        import pty,fcntl,termios,struct,select,signal,time
        from email.utils import formatdate
        import pyte
        binary=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=root/'status';status.write_text('');reading=Path(str(status)+'.read')
            entries=[('UntouchedOld',500,0),('PartialOld',800,40),('Complete',100,100),
                     ('NearlyDone',200,90),('UntouchedNew',1000,0),('PartialNew',900,40)]
            def publish(changed=None):
                reading.write_text(''.join(f'https://example.org/{name}\t{(changed or {}).get(name,value)}%\n' for name,stamp,value in entries if value))
            publish()
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>⭐ Starred</title><link>https://example.org</link><description>Test</description>'+''.join(f'<item><title>{name}</title><link>https://example.org/{name}</link><guid>{name}</guid><pubDate>{formatdate(stamp,usegmt=True)}</pubDate></item>' for name,stamp,value in entries)+'</channel></rss>')
            urls=root/'urls';urls.write_text(feed.as_uri()+'\n');config=root/'config';config.write_text('confirm-exit no\narticle-sort-order date-asc\nbind-key j down\n')
            args=[str(binary),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache.db')]
            env=dict(os.environ,TERM='xterm-256color',NEWSBOAT_DOWNLOAD_STATUS=str(status))
            subprocess.run(args+['-x','reload'],check=True,env=env,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:os.environ.update(env);os.execv(str(binary),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,0,0));screen=pyte.Screen(120,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                end=time.monotonic()+5
                while time.monotonic()<end:
                    if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
                    if predicate('\n'.join(screen.display)):return
                self.fail('\n'.join(screen.display))
            def order():
                return [name for line in screen.display[1:7] for name,stamp,value in entries if name in line]
            try:
                wait(lambda text:'Starred' in text);time.sleep(.3);os.write(fd,b'\r')
                expected=['Complete','NearlyDone','PartialNew','PartialOld','UntouchedNew','UntouchedOld']
                wait(lambda text:order()==expected and screen.cursor.y==1)
                os.write(fd,b'j');wait(lambda text:screen.cursor.y==2)
                publish({'PartialNew':95})
                expected=['Complete','PartialNew','NearlyDone','PartialOld','UntouchedNew','UntouchedOld']
                wait(lambda text:order()==expected and screen.cursor.y==3)
                self.assertIn('NearlyDone',screen.display[screen.cursor.y])
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
