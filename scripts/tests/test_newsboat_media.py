"""Protect exact identities, completed-file lookup, and playback read state."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import newsboat_media as media

URL = 'https://www.youtube.com/watch?v=abc123DEF45'


class MediaTests(unittest.TestCase):
    def test_cached_title_uses_local_article_metadata(self):
        cache=self.root/'articles.db'
        with sqlite3.connect(cache) as db:
            db.execute('CREATE TABLE rss_item(id INTEGER, url TEXT, title TEXT)')
            db.execute('INSERT INTO rss_item VALUES (1,?,?)',(URL,'Video title, not its ID'))
        with patch.dict(os.environ,NEWSBOAT_CACHE=str(cache)):
            self.assertEqual(media.cached_title(URL),'Video title, not its ID')
            self.assertEqual(media.cached_title('https://example.com/missing'),'')

    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.sample = Path(cls.fixture.name)/'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=32x32:rate=2',
                        '-t', '1', '-c:v', 'mpeg4', str(cls.sample)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.multiple(media, ROOT=self.root/'videos', CACHE=self.root/'cache',
                                    STATE=self.root/'state', URLS=self.root/'newsboat/urls')
        self.patch.start()
        media.ROOT.mkdir();media.CACHE.mkdir();media.STATE.mkdir();media.URLS.parent.mkdir()
        media.URLS.write_text('"query:Other:unread = \\"yes\\""\nhttps://example.com/feed\n')
        self.busy = patch.object(media, 'busy_paths', return_value=set())
        self.busy.start()

    def tearDown(self):
        self.busy.stop();self.patch.stop();self.temp.cleanup()

    def video(self, name, root=None):
        path=(root or media.ROOT)/name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.sample,path)
        return path

    def test_exact_delete_preserves_unrelated_videos_and_symlink_targets(self):
        selected=self.video('Selected [abc123DEF45].mp4')
        unrelated=self.video('Other [abc123DEF46].mp4')
        cache=self.video('abc123DEF45.mp4', media.CACHE)
        outside=self.root/'outside.mp4';shutil.copyfile(self.sample,outside)
        (media.ROOT/'Link [abc123DEF45].mp4').symlink_to(outside)
        self.assertEqual(media.delete(URL), 2)
        self.assertFalse(selected.exists());self.assertFalse(cache.exists())
        self.assertTrue(unrelated.exists());self.assertTrue(outside.exists())
        self.assertNotIn('abc123DEF45',media.URLS.read_text())
        self.assertIn('abc123DEF46',media.URLS.read_text())

    def test_twitch_exact_id_and_archive(self):
        selected=self.video('twitch-vods/creator - title - 1234567890.mp4')
        unrelated=self.video('twitch-vods/creator - other - 11234567890.mp4')
        archive=media.ROOT/'.downloaded-twitch-vods'
        archive.write_text('creator:1234567890\nother:11234567890\n')
        self.assertEqual(media.delete('https://www.twitch.tv/videos/1234567890'),1)
        self.assertFalse(selected.exists());self.assertTrue(unrelated.exists())
        self.assertEqual(archive.read_text(),'other:11234567890\n')

    def test_lookup_rejects_partial_fragments_invalid_and_active_files(self):
        self.video('Partial [abc123DEF45].mp4.part')
        self.video('Fragment [abc123DEF45].f137.mp4')
        (media.ROOT/'Broken [abc123DEF45].mp4').write_text('not a video')
        self.assertIsNone(media.find(URL))
        complete=self.video('Finished [abc123DEF45].mp4')
        self.assertEqual(media.find(URL),complete)
        state=dict(url=URL,status='downloading',pid=os.getpid(),process_start=media.start_time(os.getpid()))
        (media.STATE/'active.json').write_text(json.dumps(state))
        self.assertIsNone(media.find(URL))
        with self.assertRaises(ValueError):media.delete(URL)
        self.assertTrue(complete.exists())
        state['status']='cancelled'
        (media.STATE/'active.json').write_text(json.dumps(state))
        self.assertIsNone(media.find(URL))

    def test_library_is_idempotent_supports_new_names_and_preserves_other_queries(self):
        self.video('YouTube [abc123DEF45].mp4')
        self.video('twitch-vods/manual/Twitch [v1234567890].mp4')
        self.video('abc123DEF46.mp4',media.CACHE)
        original=media.URLS.read_text()
        self.assertEqual(media.rebuild(),2)
        text=media.URLS.read_text()
        self.assertIn('abc123DEF45',text);self.assertIn('1234567890',text)
        self.assertNotIn('abc123DEF46',text);self.assertTrue(text.endswith(original))
        self.assertEqual(text.count('query:📥 Downloads:'),1)
        media.rebuild();self.assertEqual(media.URLS.read_text(),text)

    def test_download_query_excludes_old_entries_for_same_video(self):
        self.video('YouTube [abc123DEF45].mp4')
        with sqlite3.connect(media.URLS.parent/'cache.db') as db:
            db.execute('CREATE TABLE rss_item (id INTEGER PRIMARY KEY, guid TEXT, url TEXT, deleted INTEGER)')
            db.executemany('INSERT INTO rss_item VALUES (?,?,?,?)', [
                (1, 'old', URL, 0), (2, 'restored', URL, 0),
                (3, 'deleted', URL, 1), (4, 'other', 'https://example.com', 0)])
        self.assertEqual(media.duplicate_download_guids({media.identity(URL)}), ['old'])
        media.rebuild()
        query = json.loads(media.URLS.read_text().splitlines()[0].removesuffix(' downloaded'))
        self.assertIn('and guid != "old"', query)
        self.assertNotIn('guid != "restored"', query)

    @unittest.skipUnless(shutil.which('mpv'), 'requires mpv')
    def test_mpv_reports_real_playback_and_failure_separately(self):
        ready=self.root/'ready'
        env=dict(os.environ,NEWSBOAT_PLAY_READY=str(ready))
        command=['mpv','--no-config','--vo=null','--ao=null','--really-quiet',
                 '--speed=10','--script='+str(SCRIPTS/'newsboat-play-ready.lua')]
        subprocess.run(command+[str(self.sample)],env=env,stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,timeout=8,check=True)
        self.assertEqual(ready.read_text(),'playing')
        ready.unlink()
        subprocess.run(command+[str(self.root/'missing.mp4')],env=env,stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,timeout=8)
        self.assertEqual(ready.read_text(),'failed')

    @unittest.skipUnless(shutil.which('newsboat'), 'requires Newsboat')
    def test_native_macro_marks_read_only_after_success_never_toggles(self):
        home=self.root/'home';(home/'scripts').mkdir(parents=True)
        player=home/'scripts/newsboat-play-video.sh'
        player.write_text('#!/bin/sh\ntouch "$HOME/called"\nexit "$RESULT"\n');player.chmod(0o755)
        shutil.copyfile(player,home/'scripts/newsboat-brave-app.sh')
        (home/'scripts/newsboat-brave-app.sh').chmod(0o755)
        (home/'scripts/newsboat-history.py').write_text('from pathlib import Path\nPath.home().joinpath("called").touch()\n')
        for helper in ('newsboat-open.py', 'newsboat_media.py'):
            shutil.copyfile(SCRIPTS/helper,home/'scripts'/helper)
        feed=self.root/'feed.xml'
        feed.write_text('<rss version="2.0"><channel><title>Fixture feed</title><link>https://example.com</link>'
                        '<description>test</description><item><title>Fixture video: creator&apos;s &quot;best&quot; &amp; more</title><link>'+URL+'</link>'
                        '<guid>fixture</guid></item></channel></rss>')
        media.URLS.write_text(feed.as_uri()+'\n')
        self.video('Downloaded [abc123DEF45].mp4')
        media.rebuild()
        config=self.root/'config';cache=self.root/'cache.db'
        source=(SCRIPTS.parents[1]/'newsboat/.newsboat/config').read_text()
        macro=next(line for line in source.splitlines() if line.startswith('macro v '))
        config.write_text('show-read-articles yes\nshow-read-feeds yes\nprepopulate-query-feeds yes\n'+macro+'\n'+'\n'.join(line for line in source.splitlines() if line.startswith(('bind o ', 'bind O ', 'bind H ')))+'\n')
        command=['newsboat','-C',str(config),'-u',str(media.URLS),'-c',str(cache)]
        env=dict(os.environ,HOME=str(home),TERM='xterm-256color')
        subprocess.run(command+['-x','reload'],env=env,capture_output=True,check=True,timeout=10)
        for initial,result,expected,key in [(1,'1',1,b',v'),(1,'0',0,b',v'),(0,'0',0,b',v'),(1,'0',0,b'O'),(1,'0',0,b'o'),(0,'0',0,b'O'),(1,'1',1,b'O'),(1,'1',1,b'o'),(0,'0',0,b'o')]:
            with sqlite3.connect(cache) as db:db.execute('update rss_item set unread=?',(initial,))
            marker=home/'called';marker.unlink(missing_ok=True)
            pid,fd=pty.fork()
            if pid==0:os.execvpe('newsboat',command,dict(env,RESULT=result))
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            data=bytearray()
            def wait_for(predicate):
                end=time.monotonic()+6
                while time.monotonic()<end:
                    if predicate():return
                    if select.select([fd],[],[],.05)[0]:
                        try:data.extend(os.read(fd,65536))
                        except OSError:break
                self.fail(repr(data[-1000:]))
            try:
                wait_for(lambda:'📥 Downloads'.encode() in data)
                os.write(fd,b'\n');wait_for(lambda:b'Fixture video' in data)
                launch_offset=len(data)
                os.write(fd,key);wait_for(marker.exists)
                time.sleep(.1)
                while select.select([fd],[],[],0)[0]:
                    data.extend(os.read(fd,65536))
                self.assertNotIn(b'\x1b[?1049l',data[launch_offset:],
                                 'Browser and video launches must keep Newsboat visible')
                os.write(fd,b'Q')
                wait_for(lambda:b'\x1b[?1049l' in data[data.rfind(b'Fixture video'):])
                os.waitpid(pid,0);pid=None
                with sqlite3.connect(cache) as db:
                    self.assertEqual(db.execute('select unread from rss_item where guid="fixture"').fetchone()[0],expected)
            finally:
                if pid:os.kill(pid,signal.SIGTERM);os.waitpid(pid,0)
                os.close(fd)


if __name__=='__main__':unittest.main()
