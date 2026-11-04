import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import wave
from unittest.mock import patch, MagicMock
import newsboat_player_reuse as reuse
from mpv_clip import Player

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'


class ReuseTests(unittest.TestCase):
    def test_only_compatible_local_players_are_reused(self):
        player = MagicMock()
        with patch.dict(os.environ, {'NEWSBOAT_PLAYLIST_CONTEXT':'', 'NEWSBOAT_RANDOM_LIFECYCLE':''}), \
             patch.object(reuse.Path, 'exists', return_value=True), \
             patch.object(reuse, 'Player', return_value=player), \
             patch('newsboat_media.playback_file', return_value=Path('/video.mp4')), \
             patch('newsboat_autoplay.plan', return_value={'enabled':False}):
            for capability in (None, {'version':1,'context':'/other-playlist'}, {'version':1,'random':'active'}):
                player.get.return_value = capability
                self.assertFalse(reuse.reuse('https://youtu.be/abcdefghijk','Video'))
            player.command.assert_not_called()
            player.get.return_value = {'version':1,'context':'','random':''}
            self.assertTrue(reuse.reuse('https://youtu.be/abcdefghijk','Video'))
            command = player.command.call_args.args
            self.assertEqual(command[:3], ('script-message-to','newsboat_playlist_playback','open-local'))
            self.assertEqual(json.loads(command[3])['path'], '/video.mp4')
            with patch('newsboat_media.playback_file', return_value=None):
                self.assertFalse(reuse.reuse('https://youtu.be/abcdefghijk','Video'))

    @unittest.skipUnless(shutil.which('mpv'), 'requires mpv')
    def test_live_player_replacement_resumes_and_unpauses(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ('newsboat-playlist-playback.lua', 'newsboat-watch-completion.lua'):
                shutil.copyfile(SCRIPTS/name,root/name)
            (root/'newsboat_autoplay.py').write_text('import json\nprint(json.dumps(dict(enabled=False)))\n')
            (root/'newsboat-up-next-thumbnail.py').write_text('raise SystemExit(1)\n')
            (root/'newsboat-playback-started.py').write_text('pass\n')
            (root/'maintenance.py').write_text('import sys\nif sys.argv[1] in ("resume","resume-spec"):print(20)\n')
            media = root/'sample.wav'
            with wave.open(str(media),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0'*8000*2*60)
            env=dict(os.environ,NEWSBOAT_MEDIA_URL='https://youtu.be/aaaaaaaaaaa',
                     NEWSBOAT_MAINTENANCE=str(root/'maintenance.py'),NEWSBOAT_QUEUE_STATUS=str(root/'queue'))
            process=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--pause',
                '--input-ipc-server='+str(root/'ipc'),'--script='+str(root/'newsboat-playlist-playback.lua'),
                '--script='+str(root/'newsboat-watch-completion.lua'),'--watch-later-directory='+str(root/'watch'),str(media)],
                env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            player=None
            try:
                deadline=time.monotonic()+5
                while not (root/'ipc').exists():
                    self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                player=Player(str(root/'ipc'))
                while not player.get('user-data/newsboat/reusable') or player.get('time-pos') is None:
                    self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                pid=player.get('pid')
                target=dict(url='https://youtu.be/bbbbbbbbbbb',path=str(media),title='New video',local=True,
                            plan=dict(enabled=False),request='test')
                player.command('script-message-to','newsboat_playlist_playback','open-local',json.dumps(target))
                while player.get('user-data/newsboat/open-request',{}).get('state')!='playing':
                    self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                self.assertEqual(player.get('pid'),pid)
                self.assertFalse(player.get('pause'))
                self.assertAlmostEqual(player.get('time-pos'),20,delta=1)
                self.assertEqual(player.get('user-data/newsboat/url'),target['url'])
                self.assertEqual(player.get('media-title'),'New video')
            finally:
                if player:player.close()
                process.terminate();process.wait(timeout=5)
