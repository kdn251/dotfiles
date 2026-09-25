import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('vods',SCRIPTS/'newsboat-vods.py')
vods=importlib.util.module_from_spec(spec);spec.loader.exec_module(vods)
media=vods.media

class VODTests(unittest.TestCase):
    def setUp(self):
        for target in ['active_rows','publish']:
            mock=patch.object(vods.progress,target,return_value=[])
            mock.start();self.addCleanup(mock.stop)
        mock=patch.object(vods.subprocess,'Popen');mock.start();self.addCleanup(mock.stop)
    def test_inventory_delete_and_archive_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);videos=root/'videos';folder=videos/'twitch-vods';folder.mkdir(parents=True)
            state=root/'state';state.mkdir();urls=root/'urls'
            urls.write_text('"query:📬 New:unread = \\"yes\\""\n"query:📥 Downloads:link = \\"none\\""\n"query:🌎 All:link = \\"none\\""\n')
            for name in ['alice - First - 123456789.mp4','alice - Newest - 123456790.mp4','bob - Busy - 123456791.mp4','bob - Partial - 123456792.mp4']:
                (folder/name).write_bytes(b'test')
            (folder/'bob - Partial - 123456792.mp4.part').touch()
            (folder/'bob - Failed - 123456794.mp4').write_bytes(b'test')
            (folder/'bob - Failed - 123456794.mp4.incomplete').touch()
            (folder/'manual').mkdir();(folder/'manual/bob - Manual - 123456793.mp4').write_bytes(b'test')
            archive=videos/'.downloaded-twitch-vods';archive.write_text('alice:123456790\n')
            with patch.multiple(vods,STATE=state,DIRECTORY=folder,INDEX=state/'vod-items.json'), patch.multiple(media,ROOT=videos,CACHE=root/'mpv-cache',STATE=state/'downloads',URLS=urls), patch.object(media,'busy_paths',return_value={(folder/'bob - Busy - 123456791.mp4').resolve()}), patch.object(media,'playable',return_value=True):
                rows=vods.rebuild()
                self.assertEqual([r['title'] for r in rows],['Newest','First'])
                self.assertEqual((state/'starred-urls.txt.vods.count').read_text(),'2\n')
                text=urls.read_text();self.assertLess(text.index('📥 Downloads'),text.index('🎬 VODs'));self.assertLess(text.index('🎬 VODs'),text.index('🌎 All'))
                view=root/'view';view.mkdir();_,config=vods.prepare_view(view)
                self.assertIn(' alice',(view/'vods.xml').read_text())
                self.assertIn('newsboat-vods.py delete %u',config.read_text())
                self.assertIn('newsboat-vods.py play %u',config.read_text())
                with patch.dict(os.environ,NEWSBOAT_VODS_VIEW_DIR=str(view)):
                    vods.delete(rows[0]['url'])
                self.assertFalse((folder/'alice - Newest - 123456790.mp4').exists())
                self.assertEqual(archive.read_text(),'alice:123456790\n')
                self.assertNotIn('123456790',(view/'urls').read_text())
                self.assertEqual((state/'starred-urls.txt.vods.count').read_text(),'1\n')
                with self.assertRaises(ValueError):vods.delete('https://www.twitch.tv/videos/123456791')
                self.assertTrue((folder/'bob - Busy - 123456791.mp4').exists())

    def test_local_playback_passes_title(self):
        with patch.object(vods,'entries',return_value=[dict(url='https://www.twitch.tv/videos/123456789',title='Stream title')]), patch.object(vods.subprocess,'run') as run:
            vods.play('https://www.twitch.tv/videos/123456789')
            self.assertEqual(run.call_args.args[0][-2:],['https://www.twitch.tv/videos/123456789','Stream title'])
            with self.assertRaises(ValueError):vods.play('https://www.twitch.tv/videos/999999999')

class VODUITests(unittest.TestCase):
    def test_home_open_delete_middle_and_last_and_return(self):
        import fcntl,pty,select,signal,struct,termios,time
        try:
            import pyte
        except ImportError:
            self.skipTest('pyte required')
        binary=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.local/lib/newsboat-paged/newsboat'))
        repo=SCRIPTS.parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root/'.newsboat';home.mkdir();(root/'scripts').symlink_to(SCRIPTS)
            install=root/'.local/lib/newsboat-paged';install.mkdir(parents=True);(install/'newsboat').symlink_to(binary)
            videos=root/'Videos/newsboat';folder=videos/'twitch-vods';folder.mkdir(parents=True)
            sample=root/'sample.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=32x32:d=1','-c:v','mpeg4',str(sample)],check=True)
            for i in range(1,4):
                path=folder/f'alice - Video{i} - 12345678{i}.mp4';path.write_bytes(sample.read_bytes());os.utime(path,(1000+i,1000+i))
            archive=videos/'.downloaded-twitch-vods';archive.write_text('alice:123456783\n')
            source=root/'feed.xml';source.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description></channel></rss>')
            config='\n'.join(line for line in (repo/'newsboat/.newsboat/config').read_text().splitlines() if not line.startswith(('include ','urls-source ','miniflux-')))+'\nurls-source local\n'
            (home/'config').write_text(config)
            (home/'urls').write_text('\n'.join(json.dumps('query:'+name+':link = "none"',ensure_ascii=False) for name in ['📬 New','📥 Downloads','🌎 All'])+'\n'+source.as_uri()+'\n')
            env=dict(os.environ,HOME=directory,XDG_STATE_HOME=str(root/'state'),NEWSBOAT_VIDEO_DIR=str(videos),NEWSBOAT_CACHE=str(home/'cache.db'),NEWSBOAT_URLS_FILE=str(home/'urls'))
            subprocess.run([str(binary),'-C',str(home/'config'),'-u',str(home/'urls'),'-c',str(home/'cache.db'),'-x','reload'],env=env,check=True,capture_output=True)
            subprocess.run([sys.executable,str(SCRIPTS/'newsboat-vods.py'),'rebuild'],env=env,check=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(env,TERM='xterm-256color');os.execv('/usr/bin/python',['python',str(SCRIPTS/'newsboat-session.py')])
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,110,0,0));screen=pyte.Screen(110,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
                    if predicate('\n'.join(screen.display)):return
                self.fail('\n'.join(screen.display))
            try:
                wait(lambda s:'🎬 VODs' in s and '🚢 Newsboat' in s)
                deadline=time.monotonic()+.5
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
                self.assertIn('3 items',next(row for row in screen.display if '🎬 VODs' in row))
                count_path=root/'state/newsboat/starred-urls.txt.vods.count'
                cursor=screen.cursor.y
                count_path.write_text('4\n')
                wait(lambda s:'4 items' in next(row for row in s.splitlines() if '🎬 VODs' in row))
                self.assertEqual(screen.cursor.y,cursor)
                count_path.write_text('3\n')
                wait(lambda s:'3 items' in next(row for row in s.splitlines() if '🎬 VODs' in row))

                os.write(fd,b':3\n\n');wait(lambda s:'Video1' in s and 'Video3' in s and screen.cursor.y == 1)
                self.assertTrue(screen.display[0].startswith(' 🎬 VODs'))
                self.assertIn('alice',screen.display[1]);self.assertIn('Video3',screen.display[1]);self.assertIn('0%',screen.display[1])
                # External progress updates redraw the badge without moving selection.
                time.sleep(.5)  # Let the empty monitor publish its initial snapshot.
                progress_path=root/'state/newsboat/download-status.tsv.vods'
                progress_path.write_text('https://www.twitch.tv/videos/123456783\t↓ 42%\n')
                wait(lambda s:'↓ 42%' in s)
                wait(lambda s:screen.cursor.y == 1)
                self.assertIn('Video3',screen.display[screen.cursor.y])
                progress_path.write_text('')
                os.write(fd,b':2\n,D');wait(lambda s:'Video2' not in s and 'Video1' in s)
                self.assertFalse((folder/'alice - Video2 - 123456782.mp4').exists())
                self.assertIn('Video1',screen.display[screen.cursor.y])
                os.write(fd,b',D');wait(lambda s:'Video1' not in s and 'Video3' in s)
                self.assertIn('Video3',screen.display[screen.cursor.y])
                os.write(fd,b'q');wait(lambda s:'🚢 Newsboat' in s and '🎬 VODs' in s)
                self.assertIn('1 items',next(row for row in screen.display if '🎬 VODs' in row))
                self.assertEqual(screen.cursor.y,3)
                self.assertEqual(archive.read_text(),'alice:123456783\n')
                os.write(fd,b'\n');wait(lambda s:'Video3' in s)
                os.write(fd,b',D');wait(lambda s:'Video3' not in s and '🎬 VODs' in s)
                os.write(fd,b'q');wait(lambda s:'🚢 Newsboat' in s)
                self.assertIn('0 items',next(row for row in screen.display if '🎬 VODs' in row))
                os.write(fd,b'\n');wait(lambda s:screen.display[0].startswith(' 🎬 VODs'))
            finally:
                def stop_tree(parent):
                    try:children=Path(f'/proc/{parent}/task/{parent}/children').read_text().split()
                    except OSError:children=[]
                    for child in children:stop_tree(int(child))
                    try:os.kill(parent,signal.SIGTERM)
                    except ProcessLookupError:pass
                stop_tree(pid);os.waitpid(pid,0);os.close(fd)

class VODResponsivenessTests(unittest.TestCase):
    def setUp(self):
        for target in ['active_rows','publish']:
            mock=patch.object(vods.progress,target,return_value=[])
            mock.start();self.addCleanup(mock.stop)
    def test_open_does_not_probe_or_wait_for_library_lock(self):
        import fcntl,time
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state';state.mkdir();folder=root/'vods';folder.mkdir()
            complete=folder/'alice - Complete - 123456789.mp4';complete.write_bytes(b'test')
            busy=folder/'alice - Busy - 123456790.mp4';busy.write_bytes(b'test')
            partial=folder/'alice - Partial - 123456791.mp4';partial.write_bytes(b'test');Path(str(partial)+'.incomplete').touch()
            index=state/'vod-items.json';index.write_text(json.dumps([dict(path=str(p),url='https://www.twitch.tv/videos/'+str(i)) for i,p in enumerate([complete,busy,partial])]))
            with (state/'.library.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                with patch.multiple(vods,STATE=state,INDEX=index),patch.object(media,'busy_paths',return_value={busy.resolve()}),patch.object(media,'playable',side_effect=AssertionError('Interactive open must not probe')),patch.object(vods.subprocess,'Popen') as launch:
                    started=time.monotonic();rows=vods.view_entries()
                    self.assertLess(time.monotonic()-started,.2)
                    self.assertEqual([row['path'] for row in rows],[str(complete)])
                    self.assertEqual(launch.call_args.args[0][-1],'refresh')

    def test_unchanged_invalid_files_are_not_repeatedly_probed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state';folder=root/'vods';folder.mkdir()
            path=folder/'alice - Broken - 123456789.mp4';path.write_bytes(b'incomplete')
            with patch.multiple(vods,STATE=state,INDEX=state/'vod-items.json',DIRECTORY=folder),patch.object(media,'inside',return_value=True),patch.object(media,'busy_paths',return_value=set()),patch.object(media,'playable',return_value=False) as probe:
                self.assertEqual(vods.scan(),[]);self.assertEqual(vods.scan(),[])
                self.assertEqual(probe.call_count,1)
                path.write_bytes(b'changed-file')
                vods.scan();self.assertEqual(probe.call_count,2)
