import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import media_chat_fullscreen as layout


class FullscreenChatTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        owner = patch.object(layout, 'OWNER', Path(tmp.name)/'owner')
        owner.start(); self.addCleanup(owner.stop)

    monitor = dict(id=0, x=0, y=0, width=2880, height=1920, scale=2,
                   specialWorkspace={'name': 'special:chatterino_chat'}, activeWorkspace={'id':3})
    player = dict(address='p', pid=10, monitor=0, fullscreen=2, workspace={'id':3}, **{'class': 'mpv'})
    chat = dict(address='c', pid=20, at=[500, 600], size=[200, 300],
                **{'class': 'com.chatterino.chatterino'})

    def test_cross_platform_handoff_keeps_canvas_and_original_settings(self):
        for service in ('Kick', 'YouTube', 'Rumble', 'Twitch'):
            chat = dict(self.chat, address='new', workspace={'id': -97},
                        **{'class': 'com.chatterino.chatterino' if service == 'Twitch' else 'newsboat-live-chat'})
            state = {'player': self.player, 'chat': self.chat, 'socket': '/tmp/mpv-twitch-ipc',
                     'properties': {'panscan': 1}, 'transition': {'service': service}}
            with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                    patch.object(layout, 'player_service', return_value=service), \
                    patch.object(layout, 'hypr', return_value=json.dumps([self.monitor])), \
                    patch.object(layout, 'style'), patch.object(layout, 'move'), \
                    patch.object(layout, 'ipc') as ipc, patch.object(layout, 'restore') as restore:
                self.assertTrue(layout.adopt_chat(state, [self.player, chat]))
                restore.assert_not_called()
                self.assertEqual(state['player']['pid'], self.player['pid'])
                self.assertEqual(state['properties'], {'panscan': 1})
                self.assertNotIn('transition', state)
                ipc.assert_called_once_with(state, 'set_property', 'video-margin-ratio-right',
                                            .3 if service == 'YouTube' else .2)

    def test_handoff_hides_chat_before_replacement_can_launch(self):
        events = []
        state = {'player': self.player, 'chat': self.chat}
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'hypr', return_value=json.dumps([self.monitor])), \
                patch.object(layout, 'hide_workspace', side_effect=lambda monitors: events.append('hide')), \
                patch.object(layout.subprocess, 'Popen', side_effect=lambda *a, **k: events.append('launch')):
            layout.STATE.write_text(json.dumps(state))
            layout.OWNER.write_text('3 0 -97')
            layout.prepare_transition('session', 'Kick', 'example')
            self.assertEqual(events, ['hide', 'launch'])
            self.assertFalse(layout.OWNER.exists())
            self.assertEqual(layout.read()['transition']['service'], 'Kick')

    def test_scaled_monitor_layout(self):
        bounds = layout.layout(self.monitor)
        self.assertEqual(bounds['at'], [1152, 0])
        self.assertEqual(bounds['size'], [288, 960])
        self.assertAlmostEqual(bounds['ratio'], 288 / 1440)
        rotated = dict(self.monitor, transform=1, x=-960)
        self.assertEqual(layout.layout(rotated)['at'], [-240, 0])

    def test_toggle_restores_video_settings_and_chat_without_leaving_fullscreen(self):
        clients = [self.player, self.chat]
        props = dict(layout.PROPERTIES, panscan=1, **{'video-margin-ratio-right': .02})
        original = props.copy()
        def ipc(state, action, key, *value):
            if action == 'get_property':
                if key == 'osd-dimensions': return {'w':2880,'h':1920,'mr':576,'mt':360,'mb':360}
                return props[key]
            self.assertEqual(action, 'set_property')
            props[key] = value[0]
        def hypr(*args):
            if args == ('-j', 'monitors'): return json.dumps([self.monitor])
            if args == ('-j', 'getoption', 'input:special_fallthrough'): return '{"int":0}'
            return 'ok'
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'socket_for', return_value='/tmp/mpv-twitch-ipc'), \
                patch.object(layout, 'ipc', side_effect=ipc), patch.object(layout, 'hypr', side_effect=hypr) as control:
            self.assertTrue(layout.begin(clients))
            self.assertTrue(props['keepaspect'])
            self.assertEqual(props['panscan'], 0)
            self.assertAlmostEqual(props['video-margin-ratio-right'], 288/1440)
            self.assertTrue(layout.close(clients))
            self.assertEqual(props, original)
            control.assert_any_call('keyword', 'input:special_fallthrough', '1')
            control.assert_any_call('keyword', 'input:special_fallthrough', '0')
            self.assertFalse(layout.STATE.exists())
            self.assertFalse(any('fullscreen' in str(c.args) for c in control.call_args_list))
            control.assert_any_call('dispatch', 'togglespecialworkspace', 'chatterino_chat')

    def test_chat_uses_full_height_even_with_letterboxed_video(self):
        bounds = layout.layout(self.monitor, video={'w':2880, 'h':1920, 'mr':576, 'mt':360, 'mb':360})
        self.assertEqual(bounds['at'], [1152, 0])
        self.assertEqual(bounds['size'], [288, 960])
        self.assertAlmostEqual(bounds['ratio'], 288/1440)

    def test_windowed_player_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'ipc') as ipc:
            self.assertFalse(layout.begin([dict(self.player, fullscreen=0), self.chat]))
            ipc.assert_not_called()

    def test_fullscreen_exit_restores_and_hides_chat(self):
        state = {'player': self.player, 'chat': self.chat}
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'read', return_value=state), patch.object(layout, 'restore') as restore:
            clients = [dict(self.player, fullscreen=0), self.chat]
            self.assertFalse(layout.maintain(clients))
            restore.assert_called_once_with(state, clients, hide=True)

    def test_workspace_round_trip_keeps_layout_and_returns_chat(self):
        state = {'player': self.player, 'chat': self.chat, 'socket':'/tmp/mpv-twitch-ipc'}
        away = dict(self.monitor, activeWorkspace={'id':4})
        back = dict(self.monitor, specialWorkspace={'name':''})
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'restore') as restore, patch.object(layout, 'move'), \
                patch.object(layout, 'ipc'), patch.object(layout, 'hypr') as hypr:
            layout.STATE.write_text(json.dumps(state))
            clients = [self.player, self.chat]
            hypr.return_value = json.dumps([away])
            self.assertTrue(layout.maintain(clients))
            self.assertTrue(layout.read()['suspended'])
            restore.assert_not_called()
            hypr.assert_any_call('dispatch', 'togglespecialworkspace', 'chatterino_chat')
            hypr.reset_mock()
            hypr.return_value = json.dumps([back])
            self.assertTrue(layout.maintain(clients))
            self.assertFalse(layout.read()['suspended'])
            restore.assert_not_called()
            hypr.assert_any_call('dispatch', 'togglespecialworkspace', 'chatterino_chat')

    def test_transition_keeps_mode_while_windows_are_replaced(self):
        state = {'transition': {'deadline': 200}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'read', return_value=state), patch.object(layout.time, 'monotonic', return_value=100), \
                patch.object(layout, 'restore') as restore:
            self.assertTrue(layout.maintain([]))
            restore.assert_not_called()

    def test_replacement_waits_for_correct_twitch_channel_and_chat(self):
        state = {'player': self.player, 'transition': {'service':'Twitch', 'name':'newstream'}}
        clients = [self.player, self.chat]
        with patch.object(layout, 'socket_for', return_value='/tmp/mpv-twitch-ipc'), \
                patch.object(Path, 'read_text', return_value='newstream'), patch.object(layout, 'ipc') as ipc:
            ipc.side_effect = ['oldstream']
            self.assertIsNone(layout.replacement(state, clients))
            ipc.side_effect = ['newstream', 12]
            self.assertEqual(layout.replacement(state, clients), self.player)
            ipc.side_effect = ['newstream']
            self.assertIsNone(layout.replacement(state, [self.player]))

    def test_cross_platform_requires_new_player(self):
        state = {'player': self.player, 'transition': {'service':'Kick', 'name':'newstream'}}
        new = dict(self.player, pid=11, address='new', fullscreen=0)
        with patch.object(layout, 'socket_for', return_value='/tmp/mpv-kick-live-ipc'), \
                patch.object(layout, 'ipc', return_value=5):
            self.assertIsNone(layout.replacement(state, [self.player]))
            self.assertEqual(layout.replacement(state, [self.player, new]), new)

    def test_prepare_does_not_enable_mode_for_regular_playback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout.subprocess, 'Popen') as spawn:
            layout.prepare_transition('session', 'Twitch', 'example')
            spawn.assert_not_called()
            self.assertFalse(layout.STATE.exists())

    def test_browser_platforms_escape_chat_workspace(self):
        for service in ('kick', 'youtube', 'rumble'):
            with self.subTest(service=service):
                trapped = dict(self.player, workspace={'id':-97})
                regular = dict(self.player, workspace={'id':3})
                def respond(*args):
                    if args == ('-j','monitors'): return json.dumps([self.monitor])
                    if args == ('-j','clients'): return json.dumps([regular])
                    return 'ok'
                with patch.object(layout, 'hypr', side_effect=respond) as hypr:
                    self.assertEqual(layout.regular_workspace(trapped)['workspace']['id'], 3)
                    hypr.assert_any_call('dispatch','movetoworkspacesilent','3,address:p')

    def test_regular_player_does_not_move_workspaces(self):
        with patch.object(layout, 'hypr') as hypr:
            self.assertEqual(layout.regular_workspace(self.player), self.player)
            hypr.assert_not_called()

    def test_fullscreen_layout_for_all_browser_chat_platforms(self):
        for service in ('kick', 'youtube', 'rumble'):
            with self.subTest(service=service), tempfile.TemporaryDirectory() as tmp:
                chat = dict(self.chat, **{'class':'newsboat-live-chat', 'workspace':{'id':-97}})
                props = dict(layout.PROPERTIES)
                def ipc(state, action, key, *value):
                    if action=='get_property':return props[key]
                    props[key]=value[0]
                def hypr(*args):
                    if args==('-j','monitors'):return json.dumps([self.monitor])
                    if args==('-j','getoption','input:special_fallthrough'):return '{"int":0}'
                    return 'ok'
                with patch.object(layout, 'STATE', Path(tmp)/'state'), \
                        patch.object(layout, 'socket_for', return_value=f'/tmp/mpv-{service}-live-ipc'), \
                        patch.object(layout, 'hypr', side_effect=hypr), patch.object(layout, 'ipc', side_effect=ipc):
                    self.assertTrue(layout.begin([self.player, chat]))
                    self.assertEqual(layout.read()['player']['workspace']['id'],3)
                    self.assertEqual(layout.read()['chat']['class'],'newsboat-live-chat')
                    self.assertAlmostEqual(props['video-margin-ratio-right'], .30 if service=='youtube' else .20)
                    self.assertTrue(layout.close([self.player, chat]))
                    self.assertEqual(props['video-margin-ratio-right'],0)
