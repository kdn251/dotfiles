import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import stream_preview as preview

class PreviewTests(unittest.TestCase):
    def test_cancel_during_resolution_cannot_launch_late_player(self):
        started=threading.Event();release=threading.Event()
        def resolve(*args):started.set();release.wait(2);return 'https://example.test/stream'
        with tempfile.TemporaryDirectory() as directory,patch.object(preview,'ROOT',Path(directory)), \
                patch.object(preview,'resolve',side_effect=resolve),patch.object(preview.subprocess,'Popen') as launch:
            player=preview.Preview('test','Twitch','https://twitch.tv/test',(0,0,400,225))
            thread=threading.Thread(target=player._run);thread.start();self.assertTrue(started.wait(1))
            player.stop();release.set();thread.join(2);launch.assert_not_called()

    def test_promote_preserves_player_without_loading_media_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);handoff=root/'handoff';session=root/'session';session.write_text('chosen')
            handoff.write_text(json.dumps(dict(name='Example',service='Twitch',created=preview.time.time(),pid=123,endpoint=str(root/'preview.sock'))))
            player=Mock();player.get.return_value=True
            window=dict(pid=123,address='p',monitor=0,**{'class':'mpv'})
            with patch.object(preview,'HANDOFF',handoff),patch.object(preview,'SESSION',session), \
                    patch.object(preview,'CANONICAL',root/'canonical'),patch.object(preview,'Player',return_value=player), \
                    patch.object(preview,'clients',return_value=[window]), \
                    patch.object(preview.subprocess,'check_output',return_value=json.dumps([dict(id=0,x=0,y=0,width=1440,height=960,scale=1)])), \
                    patch.object(preview.subprocess,'run'),patch('media_chat_fullscreen.place_player') as place:
                self.assertIsNone(preview.adopt('Other','title','','Twitch','chosen','page'))
                self.assertEqual(preview.adopt('Example','title','','Twitch','chosen','page'),123)
                self.assertFalse(handoff.exists());self.assertTrue((root/'canonical').is_symlink())
                self.assertFalse(any(c.args[0]=='loadfile' for c in player.command.call_args_list))
                player.command.assert_any_call('script-message','preview-promote','chosen','page','title','')
                place.assert_called_once_with(123)

    def test_stale_launcher_cannot_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);handoff=root/'handoff';session=root/'session';session.write_text('newer')
            handoff.write_text(json.dumps(dict(name='Example',service='Twitch',created=preview.time.time(),pid=123,endpoint='test')))
            player=Mock();player.get.return_value=True
            with patch.object(preview,'HANDOFF',handoff),patch.object(preview,'SESSION',session),patch.object(preview,'Player',return_value=player):
                self.assertIsNone(preview.adopt('Example','title','','Twitch','old','page'))
                player.command.assert_not_called()
