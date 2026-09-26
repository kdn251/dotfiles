import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
spec = importlib.util.spec_from_file_location('random_pick', SCRIPTS/'newsboat-random.py')
pick = importlib.util.module_from_spec(spec); spec.loader.exec_module(pick)


class RandomPickTests(unittest.TestCase):
    def test_unique_urls_and_empty_list(self):
        rows = [{'url': 'https://example.org/a'}, {'url': 'https://example.org/a'},
                {'url': 'newsboat-starred://empty'}, {'url': 'https://example.org/b'}]
        with patch.object(pick.secrets, 'choice', side_effect=lambda rows: rows[0]) as choose:
            pick.choose(rows)
            self.assertEqual(len(choose.call_args.args[0]), 2)
        self.assertIsNone(pick.choose([]))

    def test_only_explicit_unstar_removes(self):
        starred = Mock(); row = {'url': 'https://example.org', 'title': '<Title>'}
        for answer in ['keep', 'unstar']:
            starred.reset_mock()
            with patch('newsboat_random_prompt.request_choice', return_value=answer):
                pick.ask_to_unstar(row, starred)
            if answer == 'unstar':
                starred.enqueue_star.assert_called_once_with(row['url'], False)
            else:
                starred.enqueue_star.assert_not_called()

    def test_browser_tracks_only_new_matching_window_until_close(self):
        old = {'address': 'old', 'class': 'brave-example.org__-Default'}
        unrelated = {'address': 'other', 'class': 'brave-unrelated.org__-Default'}
        target = {'address': 'new', 'class': 'brave-example.org__-Default'}
        with patch.object(pick, 'clients', side_effect=[[old, unrelated], [old, target], [target], [old]]), patch.object(pick.time, 'sleep'):
            pick.wait_for_browser({'old'}, 'example.org')
        with self.assertRaises(ValueError):
            pick.new_browser_window([target, dict(target, address='second')], set(), 'example.org')

    def test_video_does_not_finish_until_shutdown(self):
        path = Mock()
        path.read_text.side_effect = ['', 'playing', 'playing', 'closed']
        with patch.object(pick.time, 'sleep'):
            pick.wait_for_video(path)
        self.assertEqual(path.read_text.call_count, 4)
        path.read_text.side_effect = ['failed']
        with self.assertRaises(ValueError):
            pick.wait_for_video(path)

    def test_mpv_actual_lifecycle(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); sample = root/'sample.wav'; marker = root/'status'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc', '-t', '0.3', str(sample)], check=True)
            process = subprocess.Popen(['mpv', '--no-config', '--vo=null', '--ao=null', '--keep-open=yes',
                '--script='+str(SCRIPTS/'newsboat-random-lifecycle.lua'), str(sample)],
                env=dict(os.environ, NEWSBOAT_RANDOM_LIFECYCLE=str(marker)), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic()+5
                while time.monotonic()<deadline and (not marker.exists() or marker.read_text()!='playing'):
                    time.sleep(.05)
                self.assertEqual(marker.read_text(), 'playing')
            finally:
                process.terminate(); process.wait(timeout=5)
            self.assertEqual(marker.read_text(), 'closed')

    def test_main_screen_shortcut_launches_helper_without_leaving_newsboat(self):
        import fcntl, pty, select, signal, struct, termios, time
        binary = Path(os.environ.get('NEWSBOAT_PAGED_BINARY', Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); scripts=root/'scripts'; scripts.mkdir()
            marker=root/'launched'
            (scripts/'newsboat-random.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Test feed</title><link>https://example.org</link><description>Test</description></channel></rss>')
            urls=root/'urls';urls.write_text(feed.as_uri()+'\n')
            config=root/'config';config.write_text('confirm-exit no\nbind 7 feedlist set browser "newsboat-random://starred"\n')
            command=[str(binary),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache.db')]
            subprocess.run(command+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(HOME=str(root),TERM='xterm-256color');os.execv(command[0],command)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,110,0,0))
            try:
                deadline=time.monotonic()+5;output=b''
                while time.monotonic()<deadline and b'Test feed' not in output:
                    if select.select([fd],[],[],.1)[0]:output+=os.read(fd,65536)
                self.assertIn(b'Test feed',output)
                time.sleep(.3);os.write(fd,b'7')
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and not marker.exists():time.sleep(.05)
                self.assertTrue(marker.exists(),output.decode(errors='replace'))
                os.write(fd,b'q')
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    ended,_=os.waitpid(pid,os.WNOHANG)
                    if ended:pid=None;break
                    time.sleep(.05)
                self.assertIsNone(pid,'Newsboat remained blocked after launching helper')
            finally:
                if pid:
                    os.kill(pid,signal.SIGTERM);os.waitpid(pid,0)
                os.close(fd)

    def test_prompt_choices_ignore_navigation_and_escape_keeps(self):
        from newsboat_random_prompt import Prompt, atomic_json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prompt=Prompt(root)
            for key, choice in [(b'u','unstar'),(b'k','keep'),(b'\r','keep'),(b'\x1b','keep')]:
                atomic_json(root/'request.json', dict(id='token',title='A title\x1b[2J'))
                self.assertTrue(prompt.poll())
                self.assertIn(b'Unstar', prompt.draw(110,24))
                self.assertNotIn(b'\x1b[2J', prompt.draw(110,24))
                self.assertFalse(prompt.handle(b'\x1b[A'))
                self.assertTrue(prompt.current)
                self.assertTrue(prompt.handle(key))
                self.assertEqual(json.loads((root/'answer.json').read_text())['action'],choice)
                self.assertIsNone(prompt.current)

    def test_session_prompt_and_visible_clover_inside_article_list(self):
        import fcntl,pty,select,signal,struct,termios,time
        import pyte
        binary=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);scripts=root/'scripts';scripts.mkdir();home=root/'.newsboat';home.mkdir()
            install=root/'.local/lib/newsboat-paged';install.mkdir(parents=True);(install/'newsboat').symlink_to(binary)
            helper='''import sys,os,time
from pathlib import Path
sys.path.insert(0, SCRIPTS)
from newsboat_random_prompt import request_choice
root=Path(ROOT)
(root/'launched').touch()
while not (root/'finish').exists():time.sleep(.02)
(root/'answer').write_text(request_choice(dict(title='Chosen saved item',url='https://example.org')))
'''.replace('SCRIPTS',repr(str(SCRIPTS))).replace('ROOT',repr(str(root)))
            (scripts/'newsboat-random.py').write_text(helper)
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Test feed</title><link>https://example.org</link><description>Test</description><item><title>Visible item</title><link>https://example.org/one</link><guid>one</guid><description>Text</description></item></channel></rss>')
            urls=home/'urls';urls.write_text(feed.as_uri()+'\n')
            config=home/'config';config.write_text('confirm-exit no\nbind 7 feedlist set browser "newsboat-random://starred"\n')
            env=dict(os.environ,HOME=str(root),XDG_STATE_HOME=str(root/'state'),NEWSBOAT_CACHE=str(home/'cache.db'),NEWSBOAT_URLS_FILE=str(urls),NEWSBOAT_LAST_OPENED=str(root/'last'),TERM='xterm-256color')
            subprocess.run([str(binary),'-q','-C',str(config),'-u',str(urls),'-c',str(home/'cache.db'),'-x','reload'],env=env,check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(env);os.execv(sys.executable,[sys.executable,str(SCRIPTS/'newsboat-session.py')])
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,110,0,0));screen=pyte.Screen(110,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                deadline=time.monotonic()+6
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
                    if predicate('\n'.join(screen.display)):return
                self.fail('\n'.join(screen.display))
            try:
                wait(lambda text:'🍀 Random Starred' in text)
                time.sleep(.4);os.write(fd,b'7')
                wait(lambda text:(root/'launched').exists())
                os.write(fd,b'\r');wait(lambda text:'Visible item' in text)
                (root/'finish').touch();wait(lambda text:'Chosen saved item' in text and '[u] Unstar' in text)
                os.write(fd,b'\r')
                wait(lambda text:(root/'answer').exists() and 'Chosen saved item' not in text)
                self.assertEqual((root/'answer').read_text(),'keep')
                self.assertIn('Visible item','\n'.join(screen.display))
                # Returning to the main screen still shows the clover shortcut.
                os.write(fd,b'q');wait(lambda text:'🍀 Random Starred' in text)
                (root/'answer').unlink();os.write(fd,b'7')
                wait(lambda text:'Chosen saved item' in text)
                os.write(fd,b'u');wait(lambda text:(root/'answer').exists())
                self.assertEqual((root/'answer').read_text(),'unstar')
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

class RandomShortcutTests(unittest.TestCase):
    def test_shortcut_in_feed_items_search_and_article(self):
        from test_newsboat_reconnect import reader,pyte,BINARY
        if not pyte or not BINARY.exists():self.skipTest('requires native Newsboat and pyte')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'scripts').mkdir()
            (root/'scripts/newsboat-random.py').write_text('from pathlib import Path\np=Path.home()/"picks"\nwith p.open("a") as f:f.write("pick\\n")\n')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description><item><title>Article</title><guid>one</guid><link>https://example.org/one</link><description>Article body</description></item></channel></rss>')
            binding=next(line for line in (SCRIPTS.parents[1]/'newsboat/.newsboat/config').read_text().splitlines() if line.startswith('bind 7 '))
            config='confirm-exit no\nshow-read-feeds yes\nshow-read-articles yes\n'+binding+'\n'
            with reader(root,config,feed.as_uri()+'\n') as (_,screen,send,wait):
                def count():return len((root/'picks').read_text().splitlines()) if (root/'picks').exists() else 0
                wait(lambda s:'Source' in s)
                self.assertIn('🍀 Random Starred',screen.display[-2])
                send('7');wait(lambda s:count()==1)
                send('\n');wait(lambda s:'Articles in feed' in screen.display[0])
                self.assertIn('🍀 Random Starred',screen.display[-2])
                send('7');wait(lambda s:count()==2)
                send('/Article\n');wait(lambda s:'Search' in screen.display[0])
                self.assertIn('🍀 Random Starred',screen.display[-2])
                send('7');wait(lambda s:count()==3)
                send('\n');wait(lambda s:'Article body' in s)
                self.assertIn('🍀 Random Starred',screen.display[-2])
                send('7');wait(lambda s:count()==4)
                send('?');wait(lambda s:'Help' in screen.display[0])
                self.assertIn('🍀 Random Starred',screen.display[-2])
                send('7');wait(lambda s:count()==5)
