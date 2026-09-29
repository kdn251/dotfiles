"""Playlist membership, Downloads isolation, and local episode navigation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import newsboat_media as media
import newsboat_playthroughs as library
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('playthrough_ui',SCRIPTS/'newsboat-playthroughs.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
URL='https://www.youtube.com/watch?v=abc123DEF45'
OTHER='https://www.youtube.com/watch?v=abc123DEF46'

class PlaythroughTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        mock=patch.multiple(media,ROOT=self.root/'videos',CACHE=self.root/'cache',STATE=self.root/'state/newsboat/downloads',URLS=self.root/'urls')
        mock.start();self.addCleanup(mock.stop)
        media.STATE.mkdir(parents=True);media.ROOT.mkdir();media.URLS.write_text('"query:🌎 All:unread = \\"yes\\""\n')
        self.context=self.root/'context.json'
        self.context.write_text(json.dumps(dict(url='https://www.youtube.com/playlist?list=PLseries',name='A Game',channel='Creator',rows=[
            dict(url=URL,title='Part one',source='Creator',position=1),dict(url=OTHER,title='Part two',source='Creator',position=2)])))
    def pending(self,url,status='downloading'):
        (media.STATE/(url[-11:]+'.json')).write_text(json.dumps(dict(url=url,status=status,files=[])))
    def test_explicit_membership_order_duplicate_and_pending(self):
        library.record(OTHER,self.context);library.record(URL,self.context);library.record(URL,self.context)
        self.assertEqual(len(library.groups()),1)
        self.pending(OTHER,'failed');self.pending(URL)
        group=library.groups()[0]
        self.assertEqual([r['url'] for r in group['rows']],[URL,OTHER])
        self.assertEqual((group['name'],group['channel']),('A Game','Creator'))
        self.assertEqual(len(list(library.read_groups())),1)
    def test_playlist_downloads_excluded_from_general_downloads_and_counted(self):
        library.record(URL,self.context);self.pending(URL);self.pending(OTHER)
        with patch.object(media,'candidates',return_value=[]),patch.object(media,'articles',return_value=[]):media.rebuild()
        downloads=next(line for line in media.URLS.read_text().splitlines() if line.startswith('"query:📥 Downloads:'))
        self.assertNotIn('abc123DEF45',downloads);self.assertIn('abc123DEF46',downloads)
        self.assertIn('🎮 Playthroughs',media.URLS.read_text())
        self.assertEqual((media.STATE.parent/'starred-urls.txt.playthroughs.count').read_text(),'1\n')
    def test_deletion_keeps_streamable_episodes_in_group(self):
        library.record(URL,self.context);library.record(OTHER,self.context)
        self.pending(URL);self.pending(OTHER)
        view=self.root/'view';view.mkdir()
        with patch.dict(os.environ,NEWSBOAT_PLAYTHROUGH_VIEW=str(view),NEWSBOAT_PLAYTHROUGH_ID='PLseries'):
            library.publish({})
            self.pending(URL,'deleted');library.publish({})
            self.assertIn('abc123DEF45',(view/'urls').read_text())
            self.assertIn('abc123DEF46',(view/'urls').read_text())
            self.pending(URL,'failed');library.publish({})
            self.assertIn('abc123DEF45',(view/'urls').read_text())
    def test_playthrough_persists_without_local_files(self):
        library.record(URL,self.context)
        path=media.ROOT/'Episode [abc123DEF45].mp4';path.write_bytes(b'fixture')
        index={str(path):dict(valid=True)}
        self.assertEqual(len(library.groups(index)),1)
        path.unlink();self.assertEqual(len(library.groups(index)[0]['rows']),2)

    def test_single_save_retains_full_playlist_and_migrates_old_partial_group(self):
        library.record(URL,self.context)
        group=library.groups()[0]
        self.assertEqual(len(group['rows']),2)
        self.assertEqual(group['selected_urls'],[URL])
        path=library.directory()/'PLseries.json'
        old=dict(group,rows=[group['rows'][0]])
        old.pop('schema');old.pop('selected_urls')
        path.write_text(json.dumps(old))
        cached=library.directory().parent/'browsed-playlists'
        cached.mkdir();(cached/path.name).write_text(self.context.read_text())
        library.publish({})
        updated=json.loads(path.read_text())
        self.assertEqual(len(updated['rows']),2)
        self.assertEqual(updated['selected_urls'],[URL])

    def test_average_counts_unwatched_and_matches_video_identity(self):
        library.record(URL,self.context);library.record(OTHER,self.context)
        self.pending(URL);self.pending(OTHER)
        content='https://youtu.be/abc123DEF45\t100%\n'
        self.assertIn('newsboat-playthroughs://PLseries\t50%\n',library.with_group_progress(content))
        content+=OTHER+'\t50%\n'
        self.assertIn('newsboat-playthroughs://PLseries\t75%\n',library.with_group_progress(content))
        self.assertIn('newsboat-playthroughs://PLseries\t100%\n',library.with_group_progress(content.replace('50%','100%')))
        self.pending(URL,'deleted')
        self.assertIn('newsboat-playthroughs://PLseries\t75%\n',library.with_group_progress(content))
    def test_view_names_actions_and_playlist_order(self):
        library.record(OTHER,self.context);library.record(URL,self.context)
        self.pending(URL);self.pending(OTHER)
        for ident in (None,'PLseries'):
            view=self.root/('group' if ident else 'home');view.mkdir()
            _,config,_=ui.prepare_view(view,ident)
            text=config.read_text()
            self.assertIn('article-sort-order guid-asc',text)
            if ident:
                self.assertIn('A Game — Creator',text)
                self.assertIn('delete-downloaded.sh',text)
                self.assertIn('%4w',text)
                self.assertIn('bind s ',text)
                self.assertIn('bind U ',text)
            else:
                self.assertIn('newsboat-playthroughs.py group',text)
                self.assertIn('🎮 Playthroughs',text)
                self.assertIn('macro D set browser',text)
                self.assertIn('download-playlist %u',text)
                self.assertIn('%4w  %p %t',text)
                self.assertIn('delete-downloaded.sh',text)
                self.assertNotIn('bind s ',text)
                self.assertIn('A Game — Creator',(view/'playlist.xml').read_text())

    def test_playlist_spinner_tracks_all_child_downloads(self):
        from newsboat_download_status import publish
        library.record(URL,self.context)
        target=media.STATE.parent/'download-status.tsv'
        for status in ('waiting','preparing','downloading','processing','retrying'):
            (media.STATE/'one.json').write_text(json.dumps(dict(url=URL,status=status,
                pid=os.getpid(),process_start=media.start_time(os.getpid()),percent=35)))
            publish(media.STATE)
            self.assertIn('newsboat-playthroughs://PLseries\t…\n',target.read_text())
            self.assertIn('https://www.youtube.com/playlist?list=PLseries\t…\n',target.read_text())
        (media.STATE/'one.json').write_text(json.dumps(dict(url=URL,status='failed')))
        self.pending(OTHER,'waiting')
        publish(media.STATE)
        self.assertIn('newsboat-playthroughs://PLseries\t…\n',target.read_text())
        self.pending(OTHER,'done')
        publish(media.STATE)
        self.assertNotIn('newsboat-playthroughs://',target.read_text())
        self.assertNotIn('playlist?list=',target.read_text())

    def test_local_playlist_download_queues_every_episode_without_fetching(self):
        from unittest.mock import Mock
        library.record(URL,self.context)
        downloader=Mock()
        with patch.object(ui.ui.library,'LIBRARY',self.root/'playlists'), \
                patch.object(ui.ui,'fetch') as fetch, \
                patch.object(ui.ui,'downloader_module',return_value=downloader), \
                patch.object(ui.ui.subprocess,'run'),patch.object(media,'rebuild'):
            self.assertEqual(ui.ui.download_playlist('newsboat-playthroughs://PLseries'),0)
        fetch.assert_not_called()
        self.assertEqual([call.args[0] for call in downloader.enqueue.call_args_list],[URL,OTHER])
        self.assertTrue(all(call.kwargs['defer'] for call in downloader.enqueue.call_args_list))
        downloader.start_watcher.assert_called_once()
        self.assertEqual(set(library.groups()[0]['selected_urls']),{URL,OTHER})

    def test_delete_whole_playlist_preserves_catalog_and_unrelated_files(self):
        library.record(URL,self.context)
        first=media.ROOT/'Part one [abc123DEF45].mp4';first.write_bytes(b'one')
        second=media.ROOT/'Part two [abc123DEF46].mp4';second.write_bytes(b'two')
        unrelated=media.ROOT/'Other [abc123DEF47].mp4';unrelated.write_bytes(b'other')
        inventory=[(media.identity(URL),first),(media.identity(OTHER),second),
                   (('youtube','abc123DEF47'),unrelated)]
        with patch.object(media,'candidates',return_value=inventory),patch.object(media,'rebuild') as rebuild:
            self.assertEqual(media.delete('newsboat-playthroughs://PLseries'),2)
        self.assertFalse(first.exists());self.assertFalse(second.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(len(library.groups()[0]['rows']),2)
        rebuild.assert_called_once()

    def test_creator_playlist_deletion_can_be_undone_as_a_group(self):
        import newsboat_download_undo as undo
        library.record(URL,self.context)
        first=media.ROOT/'Part one [abc123DEF45].mp4';first.write_bytes(b'one')
        second=media.ROOT/'Part two [abc123DEF46].mp4';second.write_bytes(b'two')
        url='https://www.youtube.com/playlist?list=PLseries'
        with patch.dict(os.environ,NEWSBOAT_DOWNLOAD_UNDO_TOKEN='playlist-delete',
                        NEWSBOAT_UNDO_FILE=str(self.root/'undo')), \
                patch.object(media,'candidates',return_value=[(media.identity(URL),first),(media.identity(OTHER),second)]), \
                patch.object(media,'rebuild'),patch.object(media,'rebuild_unlocked'):
            self.assertEqual(media.delete(url),2)
            self.assertFalse(first.exists());self.assertFalse(second.exists())
            undo.restore(url,'playlist-delete')
            self.assertEqual(first.read_bytes(),b'one');self.assertEqual(second.read_bytes(),b'two')

    def test_native_group_navigation_progress_delete_and_back(self):
        import fcntl,pty,select,signal,struct,termios,time,re
        from newsboat_loading import GraphicsStream
        from PIL import Image
        try:import pyte
        except ImportError:self.skipTest('requires pyte')
        binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
        library.record(OTHER,self.context);library.record(URL,self.context)
        self.pending(URL,'failed');self.pending(OTHER,'failed')
        bindir=self.root/'.local/lib/newsboat-paged';bindir.mkdir(parents=True)
        (bindir/'newsboat').symlink_to(binary);(self.root/'scripts').symlink_to(SCRIPTS)
        env=dict(os.environ,HOME=str(self.root),XDG_STATE_HOME=str(self.root/'state'),NEWSBOAT_VIDEO_DIR=str(media.ROOT),NEWSBOAT_URLS_FILE=str(media.URLS),TERM='xterm-256color')
        env['KITTY_WINDOW_ID']='1'
        thumbnails=self.root/'state/newsboat/youtube-playlists/thumbnails'
        thumbnails.mkdir(parents=True,exist_ok=True)
        for ident in ('abc123DEF45','abc123DEF46'):
            Image.new('RGB',(320,180),'red').save(thumbnails/(ident+'.png'))
        for name in list(env):
            if name.startswith('NEWSBOAT_') and name not in {'NEWSBOAT_VIDEO_DIR','NEWSBOAT_URLS_FILE'}:env.pop(name)
        library.publish({})
        config=self.root/'config'
        config.write_text('show-read-feeds yes\nconfirm-exit no\nbind-key j down\nbind-key k up\n')
        pid,fd=pty.fork()
        if pid==0:os.execve('/usr/bin/python3',['python3',str(SCRIPTS/'newsboat-session.py'),'-C',str(config),'-u',str(media.URLS),'-c',str(self.root/'cache.db')],env)
        fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,120,0,0))
        screen=pyte.Screen(120,24);stream=pyte.ByteStream(screen)
        graphics=GraphicsStream();image_seen=[]
        def wait(predicate):
            end=time.monotonic()+7
            while time.monotonic()<end:
                if select.select([fd],[],[],.05)[0]:
                    try:
                        data=graphics.feed(os.read(fd,65536))
                        if b'a=p,' in data:image_seen.append(True)
                        stream.feed(re.sub(rb'\x1b(?:_G|P).*?\x1b\\',b'',data,flags=re.S))
                    except OSError:break
                text='\n'.join(screen.display)
                if predicate(text):return
            self.fail('\n'.join(screen.display))
        try:
            wait(lambda t:'Your feeds' in t and 'Playthroughs' in t)
            os.write(fd,b'\n')
            wait(lambda t:'🎮 Playthroughs' in t and 'A Game — Creator' in t)
            wait(lambda t:bool(image_seen))
            import sqlite3
            with sqlite3.connect(media.STATE.parent/'history.db') as db:
                db.execute('CREATE TABLE IF NOT EXISTS history (url TEXT PRIMARY KEY, title TEXT, source TEXT, mode TEXT, opened REAL)')
                db.execute('INSERT INTO history VALUES (?,?,?,?,?)',(URL,'Previously opened video','Creator','video',time.time()))
            os.write(fd,b'H')
            wait(lambda t:'Previously opened video' in t)
            os.write(fd,b'q')
            wait(lambda t:'🎮 Playthroughs' in t and 'A Game — Creator' in t)
            import newsboat_watch_progress as progress
            with patch.object(progress,'STATE',media.STATE.parent),patch.dict(os.environ,NEWSBOAT_CACHE=str(self.root/'cache.db')):
                progress.record(URL,100,100)
            wait(lambda t:'50%' in t and 'A Game — Creator' in t)
            os.write(fd,b'\n')
            wait(lambda t:'Part one' in t and 'Part two' in t)
            wait(lambda t:bool(image_seen))
            os.write(fd,b'H')
            wait(lambda t:'Previously opened video' in t)
            os.write(fd,b'q')
            wait(lambda t:'Part one' in t and 'Part two' in t)
            text='\n'.join(screen.display)
            self.assertIn('0%',text)
            self.assertLess(text.index('Part one'),text.index('Part two'))
            def second_color():
                y=next(i for i,line in enumerate(screen.display) if 'Part two' in line)
                x=screen.display[y].index('Part two')
                return screen.buffer[y][x].fg
            self.assertEqual(second_color(),'8a8a8a')
            local=media.ROOT/'Part two [abc123DEF46].mp4';local.write_bytes(b'ui fixture')
            (media.STATE/'abc123DEF46.json').write_text(json.dumps(dict(url=OTHER,status='done',files=[str(local)])))
            from newsboat_download_status import publish
            with patch.dict(os.environ,NEWSBOAT_CACHE=str(self.root/'cache.db')):publish(media.STATE)
            wait(lambda t:'📥' in t and second_color()!='8a8a8a')
            os.write(fd,b',D')
            wait(lambda t:'Part one' in t and 'Part two' in t)
            os.write(fd,b'q')
            wait(lambda t:'🎮 Playthroughs' in t and 'A Game' in t)
            wait(lambda t:'50%' in t and 'A Game' in t)
            os.write(fd,b'q')
            wait(lambda t:'Your feeds' in t and 'Playthroughs' in t)
        finally:
            os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
