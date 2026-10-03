import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import newsboat_creator_images as creators
import newsboat_playlist_avatars as avatars


class CreatorImagesTests(unittest.TestCase):
    def test_rows_keep_source_metadata_and_validate_protocol(self):
        value='12;3;https://www.youtube.com/watch?v=abc123DEF45\t Alice\t23\n13;4;newsboat-feed://23\tAlice\t23\n0;9;file:///etc/passwd\n'
        self.assertEqual(avatars.parse_rows(value),[(12,3,'https://www.youtube.com/watch?v=abc123DEF45\t Alice\t23'),(13,4,'newsboat-feed://23\tAlice\t23')])

    def test_subscribed_youtube_and_feed_rows_use_channel_ids(self):
        source=dict(id=23,title='Alice',feed_url='https://www.youtube.com/feeds/videos.xml?channel_id=UC'+'a'*22,site_url='')
        with patch.object(creators,'feeds',return_value=[source]),patch.object(creators,'saved_item',return_value=None),patch.object(creators,'download_creators',return_value={}),patch.object(creators.subprocess,'run') as run:
            for request in ('https://www.youtube.com/watch?v=abc123DEF45\tAlice\t23','newsboat-feed://23\tAlice\t23'):
                self.assertEqual(creators.resolve(request),('youtube','UC'+'a'*22))
            run.assert_not_called()

    def test_local_video_and_twitch_vod_do_not_need_feeds_or_network(self):
        with patch.object(creators,'saved_item',return_value=dict(channel_id='UC'+'b'*22)),patch.object(creators,'download_creators',return_value={}),patch.object(creators,'feeds') as feeds:
            self.assertEqual(creators.resolve('https://youtu.be/abc123DEF45\tAlice\tlocal'),('youtube','UC'+'b'*22))
            self.assertEqual(creators.resolve('https://www.twitch.tv/videos/12345\t xQc\tlocal'),('twitch','xqc'))
            self.assertEqual(creators.resolve('https://www.twitch.tv/shroud\t\t'),('twitch','shroud'))
            feeds.assert_not_called()

    def test_cached_youtube_and_twitch_images_are_reused_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for platform,creator,folder in [('youtube','UC'+'c'*22,'yt-channel-avatars'),('twitch','shroud','twitch-profiles')]:
                path=root/'.cache'/folder/(creator+'.png');path.parent.mkdir(parents=True)
                Image.new('RGB',(128,128),'red').save(path)
                creators.profile.cache_clear()
                with patch.object(creators.Path,'home',return_value=root),patch.object(creators.subprocess,'run') as run:
                    self.assertTrue(creators.profile(platform,creator))
                    run.assert_not_called()
            creators.profile.cache_clear()

    def test_playlist_owner_wins_over_episode_creator(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'playlist-covers').mkdir()
            (root/'playlist-covers/PLone.json').write_text(json.dumps(dict(channel_id='UC'+'d'*22)))
            with patch.object(creators,'LIBRARY',root),patch.object(creators,'feeds') as feeds:
                self.assertEqual(creators.resolve('https://www.youtube.com/playlist?list=PLone\t\t'),('youtube','UC'+'d'*22))
                feeds.assert_not_called()

    def test_relay_draws_youtube_and_twitch_avatars_and_clears_them(self):
        import fcntl,os,pty,select,signal,struct,sys,termios,time
        import newsboat_thumbnails as thumbs
        from test_newsboat_thumbnails import run_child
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cid='UC'+'z'*22
            pngs=[]
            for folder,creator,color in [('yt-channel-avatars',cid,'red'),('twitch-profiles','xqc','blue')]:
                path=root/'.cache'/folder/(creator+'.png');path.parent.mkdir(parents=True)
                Image.new('RGB',(128,128),color).save(path);pngs.append(path.read_bytes())
            value='avatars;15;1;https://youtu.be/abc123DEF45\tAlice\t23\n15;2;https://www.twitch.tv/videos/12345\t xqc\tlocal\n'
            marker=thumbs.MARKER+value.encode()+b'\x07'
            frame = (b'\x1b[?2026h'+thumbs.transmit(42,pngs[0])+
                     b'\x1b7\x1b[2;85H\x1b_Ga=p,i=42,p=1,c=34,r=9,q=2\x1b\\\x1b8\x1b[?2026l')
            split = len(frame)//2
            child=('import os,tty,time;tty.setraw(0);os.write(1,'+repr(marker)+');os.read(0,1);'
                   'os.write(1,'+repr(frame[:split])+');time.sleep(.15);os.write(1,'+repr(frame[split:]+b'frame-done')+');'
                   'os.read(0,1);os.write(1,'+repr(thumbs.MARKER+b'avatars;\x07')+');os.read(0,1)')
            env=dict(os.environ,TERM='xterm-256color',KITTY_WINDOW_ID='1')
            for key in ('TMUX','STY','NEWSBOAT_THUMBNAIL_OWNER'):env.pop(key,None)
            size=struct.pack('HHHH',24,120,1200,480)
            creators.profile.cache_clear()
            with patch.object(creators.Path,'home',return_value=root),patch.object(creators,'saved_item',return_value=None),patch.object(creators,'download_creators',return_value={}),patch.object(creators,'FEEDS',[dict(id=23,title='Alice',feed_url='https://www.youtube.com/feeds/videos.xml?channel_id='+cid,site_url='')]):
                pid,fd=pty.fork()
                if pid==0:
                    fcntl.ioctl(0,termios.TIOCSWINSZ,size)
                    run_child([sys.executable,'-c',child],env)
            data=bytearray()
            def until(needles):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    if all(needle in data for needle in needles):return
                    if select.select([fd],[],[],.05)[0]:data.extend(os.read(fd,65536))
                self.fail('Missing avatar graphics packet')
            first=0x40000000+pid+0x100000
            try:
                until([thumbs.transmit(first+i,avatars.fit_avatar(png,size)) for i,png in enumerate(pngs)])
                until([b'\x1b[2;16H',b'\x1b[3;16H'])
                self.assertNotIn(thumbs.MARKER,data)
                data.clear();os.write(fd,b'x');until([b'frame-done'])
                # Neither an avatar placement nor another image may be inserted
                # inside the refresh PNG or its cursor-save/restore transaction.
                self.assertIn(frame,data)
                data.clear();os.write(fd,b'q')
                until([thumbs.delete(first),thumbs.delete(first+1)])
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
