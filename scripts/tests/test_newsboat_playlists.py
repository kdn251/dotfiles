"""Playlist ordering, selective imports, and real terminal navigation."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import newsboat_youtube_playlists as library
spec=importlib.util.spec_from_file_location('playlist_ui',SCRIPTS/'newsboat-playlists.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
CID='UC0VVYtw21rg2cokUystu2Dw'
URL='https://www.youtube.com/watch?v=abc123DEF45'
PLAYLIST='https://www.youtube.com/playlist?list=PLtest_123'

class PlaylistTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        mock=patch.multiple(library,LIBRARY=self.root/'library',CACHE=self.root/'main.db')
        mock.start();self.addCleanup(mock.stop)
    def test_order_hidden_videos_and_metadata_without_import(self):
        data=dict(title='Series',channel='Creator',channel_id=CID,entries=[
            dict(id='abc123DEF45',title='Episode Z'),dict(id='abc123DEF46',title='[Private video]'),
            dict(id='abc123DEF47',title='Episode A')])
        with patch.object(library,'extract',return_value=data),patch.object(library,'Client') as client:
            title,rows=library.videos(PLAYLIST)
            self.assertEqual([r['title'] for r in rows],['Episode Z','Episode A'])
            self.assertEqual([r['position'] for r in rows],[1,3])
            self.assertEqual(library.saved_item(URL)['channel_id'],CID)
            client.assert_not_called()
        with tempfile.TemporaryDirectory() as d:
            cmd,config=ui.prepare_view(d,dict(kind='playlist',name=title,rows=rows))
            self.assertIn('article-sort-order guid-asc',config.read_text())
            self.assertIn('│ %t',config.read_text())
            self.assertNotIn(r'\u2502',config.read_text())
            self.assertIn('macro d ',config.read_text())
            self.assertIn('bind s ',config.read_text())
            self.assertIn('bind V ',config.read_text())
            self.assertIn('bind U ',config.read_text())
    def test_unknown_or_nonvideo_is_not_imported(self):
        for url in ('https://example.com/article',URL,'file:///tmp/video'):
            self.assertIsNone(library.saved_item(url))
            self.assertIsNone(library.ensure_entry(url))
    def test_channel_from_saved_metadata_without_network(self):
        library.remember(dict(url=URL,title='Episode',source='Creator',channel_id=CID))
        with patch.object(library,'Client') as client:
            self.assertEqual(library.channel_for(URL),'https://www.youtube.com/channel/'+CID)
            client.assert_not_called()
    def test_only_selected_video_imported_read_and_duplicate_reused(self):
        library.remember(dict(url=URL,title='Episode',source='Creator',channel_id=CID))
        library.remember(dict(url=URL[:-1]+'6',title='Unselected',source='Creator',channel_id=CID))
        class FakeClient:
            def __init__(self):self.imports=[]
            def request(self,path,data=None,method=None):
                feed=dict(id=42,title='Creator',feed_url='https://www.youtube.com/feeds/videos.xml?channel_id='+CID)
                if path=='feeds':return [feed]
                if path.startswith('feeds/42/entries?'):return dict(entries=[],total=0)
                if path=='feeds/42/entries/import':self.imports.append(data);return dict(id=123)
                if path=='entries/123':return dict(id=123,url=URL,title='Episode',feed=feed,status='read')
                raise AssertionError(path)
        client=FakeClient()
        self.assertEqual(library.ensure_entry(URL,client),123)
        self.assertEqual(library.ensure_entry(URL,client),123)
        self.assertEqual(len(client.imports),1)
        self.assertEqual(client.imports[0]['status'],'read')
        self.assertFalse(client.imports[0]['starred'])
        self.assertNotIn('entry_id',library.saved_item(URL[:-1]+'6'))
    def test_matching_feed_entry_not_imported_again(self):
        library.remember(dict(url=URL,title='Episode',source='Creator',channel_id=CID))
        class FakeClient:
            def request(self,path,data=None,method=None):
                if path=='feeds':return [dict(id=42,feed_url='https://www.youtube.com/feeds/videos.xml?channel_id='+CID)]
                if path.startswith('feeds/42/entries?'):return dict(entries=[dict(id=77,url='https://youtu.be/abc123DEF45')],total=1)
                if path=='entries/77':return dict(id=77,url=URL)
                raise AssertionError(path)
        with patch.object(library,'cache_entry'):
            self.assertEqual(library.ensure_entry(URL,FakeClient()),77)
    def test_mpv_request_targets_originating_session(self):
        request=self.root/'request'
        with patch.dict(os.environ,NEWSBOAT_PLAYLIST_REQUEST=str(request),NEWSBOAT_WINDOW_ADDRESS='0x1234'),patch.object(ui.subprocess,'run') as run:
            ui.request(URL)
            self.assertEqual(request.read_text(),URL)
            self.assertEqual(run.call_args.args[0],['hyprctl','dispatch','focuswindow','address:0x1234'])
    def test_playlist_container_offers_whole_playlist_download(self):
        with tempfile.TemporaryDirectory() as d:
            _,config=ui.prepare_view(d,dict(kind='show',name='Creator',rows=[dict(url=PLAYLIST,title='Series')]))
            text=config.read_text()
            self.assertIn('Open playlist',text)
            self.assertNotIn('bind s ',text)
            self.assertIn('macro d ',text)
            self.assertIn('download-playlist %u',text)
            self.assertIn('open-in-browser-noninteractively',text)

    def test_whole_playlist_queues_unique_videos_and_persists_membership(self):
        import newsboat_playthroughs, newsboat_media
        row=dict(url=URL,title='Episode',source='Creator',position=1)
        data=dict(url=PLAYLIST,name='Series',channel='Creator',rows=[row,row])
        downloader=Mock()
        with patch.object(ui,'fetch',return_value=data),patch.object(ui,'downloader_module',return_value=downloader),patch.object(ui.subprocess,'run'),patch.object(newsboat_playthroughs,'record_rows') as record,patch.object(newsboat_media,'rebuild') as rebuild:
            self.assertEqual(ui.download_playlist(PLAYLIST),0)
            record.assert_called_once_with(data,[row])
            downloader.enqueue.assert_called_once_with(URL,'Episode',batch=PLAYLIST,defer=True)
            downloader.start_watcher.assert_called_once()
            rebuild.assert_called_once()
        with patch.object(ui,'background') as background:
            self.assertEqual(ui.main(['download-playlist',PLAYLIST]),0)
            background.assert_called_once_with(['download-playlist',PLAYLIST])

class PlaylistTerminalTests(unittest.TestCase):
    def test_open_search_back_and_episode_order(self):
        import fcntl,pty,select,signal,struct,termios,time
        try:import pyte
        except ImportError:self.skipTest('pyte required')
        binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
        if not binary.exists():self.skipTest('custom Newsboat required')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'state';lib=state/'newsboat/youtube-playlists';(lib/'videos').mkdir(parents=True)
            (lib/'videos/abc123DEF45.json').write_text(json.dumps(dict(url=URL,title='Seed',channel_id=CID)))
            (root/'.local/bin').mkdir(parents=True);ytdlp=root/'.local/bin/yt-dlp'
            ytdlp.write_text('''#!/usr/bin/python3
import json,sys,time
time.sleep(.4)
if sys.argv[-1].endswith('/playlists'):
 print(json.dumps(dict(channel='Test Creator',entries=[dict(title='First Series',url='https://www.youtube.com/playlist?list=PLfirst'),dict(title='Second Series',url='https://www.youtube.com/playlist?list=PLsecond')])))
else:
 print(json.dumps(dict(title='Second Series',channel='Test Creator',channel_id='UC0VVYtw21rg2cokUystu2Dw',entries=[dict(id='abc123DEF45',title='Zebra episode first'),dict(id='abc123DEF46',title='Apple episode second')])) )
''');ytdlp.chmod(0o755)
            bindir=root/'.local/lib/newsboat-paged';bindir.mkdir(parents=True);(bindir/'newsboat').symlink_to(binary)
            (root/'scripts').symlink_to(SCRIPTS)
            env=dict(os.environ,HOME=d,XDG_STATE_HOME=str(state),TERM='xterm-256color',PATH=str(bindir)+':'+os.environ['PATH'])
            for name in list(env):
                if name.startswith('NEWSBOAT_'):env.pop(name)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.clear();os.environ.update(env);os.execv(sys.executable,[sys.executable,str(SCRIPTS/'newsboat-playlists.py'),'show',URL])
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,0,0))
            screen=pyte.Screen(120,24);stream=pyte.ByteStream(screen)
            captured=bytearray()
            def wait(predicate):
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.1)[0]:
                        try:data=os.read(fd,65536)
                        except OSError:break
                        captured.extend(data)
                        stream.feed(data)
                    if predicate('\n'.join(screen.display)):return
                self.fail('\n'.join(screen.display))
            try:
                wait(lambda t:'loading playlists' in t)
                self.assertIn('\\______________________/', '\n'.join(screen.display))
                self.assertNotIn(b'\x1b[?1049h',captured)
                wait(lambda t:'Playlists · Test Creator' in t and 'Second Series' in t)
                self.assertNotIn(b'\x1b[?1049l',captured)
                captured.clear()
                os.write(fd,b'j\n')
                wait(lambda t:'loading playlist videos' in t)
                self.assertLess(captured.index(b'\x1b[?2026h'),captured.index(b'\x1b[2J'))
                # The first release must contain the painted loader, rather
                # than expose Newsboat's reset or the screen behind it.
                self.assertIn(b'loading playlist videos',captured.split(b'\x1b[?2026l')[0])
                self.assertIn('\\______________________/', '\n'.join(screen.display))
                wait(lambda t:'Playlist · Second Series' in t and 'Zebra episode first' in t)
                text='\n'.join(screen.display)
                self.assertLess(text.index('Zebra episode first'),text.index('Apple episode second'))
                os.write(fd,b'/Apple\n')
                wait(lambda t:'Search results' in t and 'Apple episode second' in t)
                os.write(fd,b'q');time.sleep(.1);os.write(fd,b'q')
                wait(lambda t:'Playlists · Test Creator' in t)
                os.write(fd,b'\n')
                wait(lambda t:'Playlist · Second Series' in t)
                os.write(fd,b'q')
                wait(lambda t:'Playlists · Test Creator' in t)
                os.write(fd,b'k\n')
                wait(lambda t:'loading playlist videos' in t)
                os.write(fd,b'q')
                wait(lambda t:'Playlists · Test Creator' in t and 'First Series' in t)
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
