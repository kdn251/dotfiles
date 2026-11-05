import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import stream_preview as preview

class PreviewTests(unittest.TestCase):
    def test_current_stream_is_not_previewed(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(preview,'ROOT',Path(directory)), \
                patch.object(preview,'clients',return_value=[{'class':'mpv','pid':123}]), \
                patch.object(preview,'player_identity',return_value=('Twitch','Example')), \
                patch.object(preview.subprocess,'Popen') as spawn,patch.object(preview,'resolve') as resolve:
            player=preview.Preview('example','Twitch','https://twitch.tv/example',(0,0,400,225))
            player._run()
            spawn.assert_not_called();resolve.assert_not_called()
            self.assertFalse(preview.already_watching('example','Kick'))
            self.assertFalse(preview.already_watching('other','Twitch'))

    def test_closed_player_or_other_preview_does_not_suppress_preview(self):
        with patch.object(preview,'clients',return_value=[{'class':'stream-preview'}]), \
                patch.object(preview,'player_identity') as identity:
            self.assertFalse(preview.already_watching('example','Twitch'))
            identity.assert_not_called()
        with patch.object(preview,'clients',return_value=[{'class':'mpv'}]), \
                patch.object(preview,'player_identity',return_value=None):
            self.assertFalse(preview.already_watching('example','Twitch'))

    def test_cancel_during_resolution_cannot_launch_late_player(self):
        started=threading.Event();release=threading.Event()
        def resolve(*args):started.set();release.wait(2);return 'https://example.test/stream'
        process=Mock();process.pid=123;process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory,patch.object(preview,'ROOT',Path(directory)), \
                patch.object(preview,'resolve',side_effect=resolve),patch.object(preview.subprocess,'Popen',return_value=process), \
                patch.object(preview,'clients',return_value=[dict(pid=123,address='preview')]), \
                patch.object(preview.subprocess,'run'),patch.object(preview.subprocess,'check_output',return_value='[]'),patch.object(preview,'Player') as ipc:
            player=preview.Preview('test','Twitch','https://twitch.tv/test',(0,0,400,225))
            thread=threading.Thread(target=player._run);thread.start();self.assertTrue(started.wait(1))
            player.stop();release.set();thread.join(2)
            process.terminate.assert_called_once()
            ipc.assert_not_called()  # A stale resolver must never load media after cancellation.

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
                    patch.object(preview.subprocess,'run'),patch('pip_geometry.settings',return_value=([12]*4,1)),patch('media_chat_fullscreen.place_player') as place:
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

    def test_enter_places_ready_preview_before_launcher_adoption(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(preview,'ROOT',root),patch.object(preview,'HANDOFF',root/'handoff'), \
                    patch.object(preview,'Player') as ipc,patch.object(preview.subprocess,'run') as move, \
                    patch.object(preview,'clients',return_value=[]), \
                    patch.object(preview.threading.Thread,'start'):
                item=preview.Preview('example','Twitch','https://twitch.tv/example',(0,0,400,225))
                item.process=Mock(pid=123);item.process.poll.return_value=None
                item.landing=('0x123',883,642,547,308)
                ipc.return_value.get.return_value=True
                self.assertTrue(item.handoff())
                move.assert_called_once()
                self.assertEqual(move.call_args.args[0][:2],['/usr/bin/hyprctl','eval'])
                self.assertIn('x=883,y=642',move.call_args.args[0][2])
                self.assertTrue(json.loads((root/'handoff').read_text())['landed'])
                ipc.return_value.command.assert_not_called()
                item.process.terminate.assert_not_called()

    def test_fullscreen_handoff_never_lands_in_corner(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(preview,'ROOT',root),patch.object(preview,'HANDOFF',root/'handoff'),                     patch.object(preview,'Player') as ipc,patch.object(preview.subprocess,'run') as move,                     patch.object(preview,'clients',return_value=[dict(pid=456,fullscreen=2,**{'class':'mpv'})]),                     patch.object(preview.threading.Thread,'start'):
                item=preview.Preview('example','Twitch','https://twitch.tv/example',(0,0,400,225))
                item.process=Mock(pid=123);item.process.poll.return_value=None
                item.landing=('0x123',883,642,547,308)
                ipc.return_value.get.return_value=True
                self.assertTrue(item.handoff())
                move.assert_not_called()
                self.assertNotIn('landed',json.loads((root/'handoff').read_text()))

    def test_fullscreen_adoption_saves_return_geometry_without_showing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);handoff=root/'handoff';session=root/'session';session.write_text('chosen')
            handoff.write_text(json.dumps(dict(name='Example',service='Twitch',created=preview.time.time(),pid=123,endpoint=str(root/'preview.sock'))))
            player=Mock();player.get.return_value=True
            window=dict(pid=123,address='p',monitor=0,at=[10,10],size=[480,270],fullscreen=0,**{'class':'mpv'})
            old=dict(pid=456,address='old',fullscreen=2,**{'class':'mpv'})
            toggle=Mock(side_effect=lambda *args: window.update(fullscreen=2))
            with patch.object(preview,'HANDOFF',handoff),patch.object(preview,'SESSION',session),                     patch.object(preview,'CANONICAL',root/'canonical'),patch.object(preview,'Player',return_value=player),                     patch.object(preview,'clients',return_value=[old,window]),                     patch.object(preview.os,'pidfd_open',side_effect=lambda pid: self.retire_after_fullscreen(window, pid)),                     patch('media_chat_fullscreen.socket_for',return_value='old.sock'),                     patch.object(preview.subprocess,'check_output',return_value=json.dumps([dict(id=0,x=0,y=0,width=1440,height=960,scale=1)])),                     patch.object(preview.subprocess,'run') as move,patch('pip_geometry.settings',return_value=([12]*4,1)),                     patch('media_chat_fullscreen.place_player') as place,                     patch.object(preview.runpy,'run_path',return_value={'toggle':toggle}):
                self.assertEqual(preview.adopt('Example','title','','Twitch','chosen','page'),123)
                move.assert_not_called()
                toggle.assert_called_once()
                saved=toggle.call_args.args[0]
                self.assertNotEqual(saved['at'],window['at'])
                self.assertEqual(saved['size'],[547,308])
                place.assert_called_once_with(123,align=False)

    def retire_after_fullscreen(self, window, pid):
        self.assertEqual(pid,456)
        self.assertEqual(window['fullscreen'],2,
                         'Previous stream closed before replacement covered desktop')
        raise ProcessLookupError

    def test_windowed_handoff_uses_current_player_position_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            old=dict(pid=456,fullscreen=0,at=[45,67],size=[800,450],**{'class':'mpv'})
            with patch.object(preview,'ROOT',root),patch.object(preview,'HANDOFF',root/'handoff'),                     patch.object(preview,'Player') as ipc,patch.object(preview.subprocess,'run') as move,                     patch.object(preview,'clients',return_value=[old]),patch.object(preview.threading.Thread,'start'):
                item=preview.Preview('example','Twitch','https://twitch.tv/example',(0,0,400,225))
                item.process=Mock(pid=123);item.process.poll.return_value=None
                item.landing=('0x123',883,642,547,308)
                ipc.return_value.get.return_value=True
                self.assertTrue(item.handoff())
                script=move.call_args.args[0][2]
                self.assertIn('x=45,y=67',script)
                self.assertIn('x=800,y=450',script)
                self.assertNotIn('x=883,y=642',script)

    def test_adoption_preserves_old_geometry_without_default_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);handoff=root/'handoff';session=root/'session';session.write_text('chosen')
            handoff.write_text(json.dumps(dict(name='Example',service='Twitch',created=preview.time.time(),pid=123,endpoint=str(root/'preview.sock'),landed=True)))
            player=Mock();player.get.return_value=True
            window=dict(pid=123,address='p',monitor=0,at=[883,642],size=[547,308],fullscreen=0,**{'class':'mpv'})
            old=dict(pid=456,address='old',fullscreen=0,at=[45,67],size=[800,450],**{'class':'mpv'})
            with patch.object(preview,'HANDOFF',handoff),patch.object(preview,'SESSION',session),                     patch.object(preview,'CANONICAL',root/'canonical'),patch.object(preview,'Player',return_value=player),                     patch.object(preview,'clients',return_value=[old,window]),                     patch.object(preview.os,'pidfd_open',side_effect=ProcessLookupError),                     patch('media_chat_fullscreen.socket_for',return_value='old.sock'),                     patch.object(preview.subprocess,'run') as move,                     patch('media_chat_fullscreen.place_player') as place:
                self.assertEqual(preview.adopt('Example','title','','Twitch','chosen','page'),123)
                batch=move.call_args.args[0][-1]
                self.assertIn('exact 800 450',batch)
                self.assertIn('exact 45 67',batch)
                place.assert_called_once_with(123,align=False)
