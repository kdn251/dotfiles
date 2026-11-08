import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import media_chat_fullscreen as layout


class FullscreenChatTests(unittest.TestCase):
    def setUp(self):
        capture=patch('stream_preview.capture_switch')
        capture.start();self.addCleanup(capture.stop)
        sidebar=patch('stream_sidebar.prepare_transfer')
        sidebar.start();self.addCleanup(sidebar.stop)
        cover=patch.object(layout,'cover_chat')
        cover.start();self.addCleanup(cover.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = patch.object(layout, 'ROOT', Path(tmp.name))
        root.start(); self.addCleanup(root.stop)
        owner = patch.object(layout, 'OWNER', Path(tmp.name)/'owner')
        owner.start(); self.addCleanup(owner.stop)
        preference = patch.object(layout, 'PREFERENCE', Path(tmp.name)/'preference')
        preference.start(); self.addCleanup(preference.stop)

    monitor = dict(id=0, x=0, y=0, width=2880, height=1920, scale=2,
                   specialWorkspace={'name': 'special:chatterino_chat'}, activeWorkspace={'id':3})
    player = dict(address='p', pid=10, monitor=0, fullscreen=2, workspace={'id':3}, **{'class': 'mpv'})
    chat = dict(address='c', pid=20, at=[500, 600], size=[200, 300],
                **{'class': 'com.chatterino.chatterino'})

    def test_chat_slide_direction_tracks_player_side_and_visibility(self):
        chat=dict(self.chat,workspace={'name':'special:chatterino_chat'},size=[288,960])
        for fullscreen,player_x,chat_x,opening,closing in (
                (2,0,1152,'right','left'),
                (0,10,600,'left','right'),
                (0,900,600,'right','left')):
            player=dict(self.player,fullscreen=fullscreen,at=[player_x,100])
            pane=dict(chat,at=[chat_x,100])
            with self.subTest(fullscreen=fullscreen,player_x=player_x):
                hidden=dict(self.monitor,specialWorkspace={'name':''})
                self.assertEqual(layout.chat_slide_style([player,pane],[hidden]),f'slide {opening} 20%')
                self.assertEqual(layout.chat_slide_style([player,pane],[self.monitor]),f'slide {closing} 20%')

    def test_native_slide_defers_margin_until_chat_is_visible(self):
        (layout.ROOT/'media-chat-slide-enabled').touch()
        state={'player':self.player,'socket':'/tmp/test-mpv'}
        def update(command,*args,**kwargs):
            command('set_property','video-margin-ratio-right',.2)
            command('set_property','keepaspect',True)
        with patch('media_panel_layout.update',side_effect=update),patch.object(layout,'ipc') as ipc:
            layout.panel_space(state,.2,animate=True)
            ipc.assert_called_once_with(state,'set_property','keepaspect',True)
            self.assertEqual((layout.ROOT/'media-chat-slide-socket').read_text(),'/tmp/test-mpv\n')

    def test_new_chat_stages_hidden_only_in_fullscreen(self):
        for fullscreen in (0,2):
            with self.subTest(fullscreen=fullscreen),patch.object(layout,'hypr',side_effect=[json.dumps([dict(self.player,fullscreen=fullscreen)]),json.dumps([self.monitor])]),patch.object(layout,'hide_workspace') as hide:
                layout.prepare_chat_window()
                self.assertEqual(hide.call_count,1 if fullscreen else 0)

    def test_chat_retirement_moves_before_close_under_focus_guard(self):
        with patch.object(layout,'hypr') as hypr:
            layout.retire_chat_window('0x123')
        command,script=hypr.call_args.args
        self.assertEqual(command,'eval')
        self.assertLess(script.index('on_focus_under_fullscreen=0'),script.index('window.move'))
        self.assertLess(script.index('window.move'),script.index('window.close'))
        self.assertIn('special:media_chat_closing',script)
        self.assertIn('on_focus_under_fullscreen=previous',script)

    def test_new_stream_is_pinned_once_unless_fullscreen_or_already_pinned(self):
        for pinned, fullscreen, expected in [(False, 0, True), (True, 0, False), (False, 2, False)]:
            player = dict(self.player, pinned=pinned, fullscreen=fullscreen, floating=True)
            with patch.object(layout, 'hypr', side_effect=lambda *args: json.dumps([player]) if args == ('-j', 'clients') else '[]') as hypr, \
                    patch.object(layout, 'regular_workspace', return_value=player), \
                    patch.object(layout, 'read', return_value=None):
                layout.place_player(player['pid'])
                calls = [c.args for c in hypr.call_args_list if c.args[:2] == ('dispatch', 'pin')]
                self.assertEqual(calls, [('dispatch', 'pin', 'address:p')] if expected else [])

    def test_reopened_video_is_pinned_without_repositioning(self):
        player = dict(self.player, pinned=False, fullscreen=0, floating=True)
        with patch.object(layout, 'hypr', return_value=json.dumps([player])) as hypr, \
                patch.object(layout, 'regular_workspace', return_value=player), \
                patch.object(layout, 'read', return_value=None):
            layout.place_player(player['pid'], align=False)
        self.assertEqual([c.args for c in hypr.call_args_list],
                         [('-j', 'clients'), ('dispatch', 'pin', 'address:p')])

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
                ipc.assert_any_call(state, 'set_property', 'video-margin-ratio-right',
                                            .2)

    def test_handoff_keeps_chat_visible_while_replacement_loads(self):
        events = []
        state = {'player': self.player, 'chat': self.chat}
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'hypr', return_value=json.dumps([self.monitor])), \
                patch.object(layout, 'hide_workspace', side_effect=lambda monitors: events.append('hide')), \
                patch.object(layout.subprocess, 'Popen', side_effect=lambda *a, **k: events.append('launch')):
            layout.STATE.write_text(json.dumps(state))
            layout.OWNER.write_text('3 0 -97')
            layout.prepare_transition('session', 'Kick', 'example')
            self.assertEqual(events, ['launch'])
            self.assertFalse(layout.OWNER.exists())
            self.assertEqual(layout.read()['transition']['service'], 'Kick')

    def test_theater_returns_after_unfullscreen_but_only_for_same_player(self):
        state = {'player': self.player, 'chat': self.chat}
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'read', return_value=state), patch.object(layout, 'restore'):
            self.assertFalse(layout.maintain([dict(self.player, fullscreen=0), self.chat]))
        self.assertEqual(json.loads(layout.PREFERENCE.read_text())['pid'], self.player['pid'])
        with patch.object(layout, 'hypr', return_value=json.dumps([self.monitor])), \
                patch.object(layout.subprocess, 'Popen') as launch:
            self.assertFalse(layout.resume_theater([dict(self.player, fullscreen=0)]))
            launch.assert_not_called()
            self.assertTrue(layout.resume_theater([self.player]))
            launch.assert_called_once()
            self.assertTrue(layout.resume_theater([self.player]))
            launch.assert_called_once()  # No duplicate openers during startup.
            self.assertFalse(layout.resume_theater([dict(self.player, pid=999)]))
            self.assertFalse(layout.PREFERENCE.exists())

    def test_windowed_toggle_preserves_application_focus(self):
        player=dict(self.player,fullscreen=0,pinned=True)
        def reply(*args):
            if args==('-j','clients'):return json.dumps([player,self.chat])
            if args==('-j','monitors'):return json.dumps([self.monitor])
            if args==('-j','activewindow'):return json.dumps({'address':'0xbeef','class':'kitty'})
            if args[0]=='eval' and 'toggle_special' in args[1]:
                self.assertEqual((layout.ROOT/'media-chat-restore-focus').read_text().strip(),'0xbeef')
            return 'ok'
        with patch.object(layout,'hypr',side_effect=reply) as call:
            layout.toggle_workspace()
            transaction=call.call_args.args[1]
            self.assertIn('toggle_special',transaction)
            self.assertNotIn('hl.dsp.focus',transaction)
            self.assertFalse((layout.ROOT/'media-chat-restore-focus').exists())

    def test_windowed_chat_follows_only_pinned_player_and_stops_when_hidden(self):
        player=dict(self.player,fullscreen=0,pinned=True)
        chat=dict(self.chat,workspace={'name':'special:chatterino_chat'})
        monitor=dict(self.monitor,specialWorkspace={'name':''},activeWorkspace={'id':99})
        layout.windowed_chat_path().write_text(json.dumps({'pid':player['pid'],'address':player['address']}))
        with patch.object(layout,'hypr',return_value=json.dumps([monitor])), patch.object(layout,'toggle_on_monitor') as reveal:
            layout.maintain_windowed_chat([dict(player,pinned=False),chat])
            reveal.assert_not_called()
            layout.maintain_windowed_chat([player,chat])
            reveal.assert_called_once_with(monitor,[monitor],animate=False)
            reveal.reset_mock()
            layout.windowed_chat_path().unlink()
            layout.maintain_windowed_chat([player,chat])
            reveal.assert_not_called()

    def test_follower_cannot_race_manual_chat_toggle(self):
        import fcntl
        with (layout.ROOT/'media-chat-windowed.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with patch.object(layout,'_maintain_windowed_chat') as maintain:
                layout.maintain_windowed_chat([])
                maintain.assert_not_called()
        with patch.object(layout,'_maintain_windowed_chat') as maintain:
            layout.maintain_windowed_chat([])
            maintain.assert_called_once_with([])

    def test_unpinned_chat_hides_away_and_returns_to_its_workspace(self):
        player=dict(self.player,fullscreen=0,pinned=False)
        chat=dict(self.chat,workspace={'name':'special:chatterino_chat'})
        layout.windowed_chat_path().write_text(json.dumps({'pid':player['pid'],'address':player['address']}))
        away=dict(self.monitor,activeWorkspace={'id':99})
        home=dict(self.monitor,specialWorkspace={'name':''})
        with patch.object(layout,'hypr',return_value=json.dumps([away])), patch.object(layout,'toggle_on_monitor') as toggle:
            layout.maintain_windowed_chat([player,chat])
            toggle.assert_called_once_with(away,[away],animate=False)
            self.assertTrue(layout.windowed_chat_path().exists())
        with patch.object(layout,'hypr',return_value=json.dumps([home])), patch.object(layout,'toggle_on_monitor') as toggle:
            layout.maintain_windowed_chat([player,chat])
            toggle.assert_called_once_with(home,[home],animate=False)

    def test_instant_reveal_marker_is_scoped_to_dispatch_even_on_failure(self):
        marker=layout.ROOT/'media-chat-slide-instant'
        def dispatch(*args):
            if args[:1]==('-j',):return '[]'
            if args[0]=='eval' and 'toggle_special' in args[1]:
                self.assertTrue(marker.exists())
                raise RuntimeError('dispatch failed')
            return ''
        with patch.object(layout,'hypr',side_effect=dispatch):
            with self.assertRaises(RuntimeError):layout.toggle_workspace(animate=False)
        self.assertFalse(marker.exists())

    def test_fullscreen_return_reuses_loaded_chat_without_opener(self):
        layout.remember_theater(self.player,self.chat)
        monitor=dict(self.monitor,specialWorkspace={'name':''})
        with patch.object(layout,'hypr',return_value=json.dumps([monitor])), \
                patch.object(layout,'begin',return_value=True) as begin, \
                patch.object(layout,'toggle_on_monitor') as reveal, \
                patch.object(layout,'focus_player') as focus, \
                patch.object(layout.subprocess,'Popen') as launch:
            self.assertTrue(layout.resume_theater([self.player,self.chat]))
            begin.assert_called_once_with([self.player,self.chat],animate=False)
            reveal.assert_called_once_with(monitor,[monitor],animate=False)
            focus.assert_called_once()
            launch.assert_not_called()

    def test_explicit_mod_c_returns_to_normal_fullscreen(self):
        state = {'player': self.player, 'chat': self.chat}
        layout.remember_theater(self.player)
        with tempfile.TemporaryDirectory() as tmp, patch.object(layout, 'STATE', Path(tmp)/'state'), \
                patch.object(layout, 'read', return_value=state), patch.object(layout, 'restore'):
            self.assertTrue(layout.close([self.player, self.chat]))
        self.assertFalse(layout.PREFERENCE.exists())
        with patch.object(layout.subprocess, 'Popen') as launch:
            self.assertFalse(layout.resume_theater([self.player]))
            launch.assert_not_called()

    def test_focus_returns_to_video_only_on_its_visible_workspace(self):
        state = {'player': self.player}
        def hypr(*args):
            if args == ('-j', 'clients'): return json.dumps([self.player])
            if args == ('-j', 'monitors'): return json.dumps([self.monitor])
            return 'ok'
        with patch.object(layout, 'read', return_value=state), \
                patch.object(layout, 'hypr', side_effect=hypr) as control:
            layout.focus_player()
            control.assert_any_call('dispatch', 'focuswindow', 'address:p')
        with patch.object(layout, 'read', return_value=state), \
                patch.object(layout, 'hypr', side_effect=[json.dumps([self.player]),
                    json.dumps([dict(self.monitor, activeWorkspace={'id': 8})])]) as control:
            layout.focus_player()
            self.assertEqual(control.call_count, 2)

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
                return props.get(key)
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
            self.assertEqual({key:props[key] for key in original}, original)
            control.assert_any_call('keyword', 'input:special_fallthrough', '1')
            control.assert_any_call('keyword', 'input:special_fallthrough', '0')
            self.assertFalse(layout.STATE.exists())
            self.assertFalse(any('window.fullscreen' in str(c.args) for c in control.call_args_list))
            self.assertTrue(any(c.args[0]=='eval' and 'workspace.toggle_special' in c.args[1] for c in control.call_args_list))

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
                patch.object(layout, 'ipc'), patch.object(layout, 'focus_player') as focus, \
                patch.object(layout, 'hypr') as hypr:
            layout.STATE.write_text(json.dumps(state))
            clients = [self.player, self.chat]
            hypr.return_value = json.dumps([away])
            self.assertTrue(layout.maintain(clients))
            self.assertTrue(layout.read()['suspended'])
            restore.assert_not_called()
            self.assertTrue(any(c.args[0]=='eval' and 'workspace.toggle_special' in c.args[1] for c in hypr.call_args_list))
            hypr.reset_mock()
            hypr.return_value = json.dumps([back])
            self.assertTrue(layout.maintain(clients))
            self.assertFalse(layout.read()['suspended'])
            focus.assert_not_called()
            restore.assert_not_called()
            self.assertTrue(any(c.args[0]=='eval' and 'workspace.toggle_special' in c.args[1] for c in hypr.call_args_list))

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

    def test_chat_waits_for_staged_handoff_commit(self):
        for service in ('Twitch','YouTube','Kick','Rumble'):
            with self.subTest(service=service):
                state={'player':self.player,'transition':{'service':service,'name':'next','session':'selected'}}
                new=dict(self.player,pid=11,address='new',initialClass='stream-staging',fullscreen=0)
                properties={'user-data/twitch-channel':'next','time-pos':12}
                with patch('stream_player_identity.identity',return_value=(service,'next')), \
                        patch.object(layout,'socket_for',return_value='private.sock'), \
                        patch.object(Path,'read_text',return_value='next'), \
                        patch.object(layout,'ipc',side_effect=lambda state,op,key:properties.get(key)):
                    self.assertIsNone(layout.replacement(state,[new,self.chat]))
                    properties['user-data/stream-handoff-complete']='older-session'
                    self.assertIsNone(layout.replacement(state,[new,self.chat]))
                    properties['user-data/stream-handoff-complete']='selected'
                    self.assertEqual(layout.replacement(state,[new,self.chat]),new)

    def test_chat_cleanup_rechecks_fullscreen_instead_of_stale_snapshot(self):
        current=dict(self.player,fullscreen=0)
        def ipc(state,action,key,*args):
            if action=='set_property':current['fullscreen']=2
            else:return bool(current['fullscreen'])
        with patch.object(layout,'hypr',side_effect=lambda *args:json.dumps([current])), \
                patch.object(layout,'socket_for',return_value='player.sock'), \
                patch.object(layout,'ipc',side_effect=ipc) as command:
            result=layout.restore_transition_fullscreen(dict(self.player,fullscreen=2))
            self.assertEqual(result['fullscreen'],2)
            self.assertTrue(any(c.args[1:]==('set_property','fullscreen',True) for c in command.call_args_list))

    def test_chat_cleanup_renews_stale_mpv_fullscreen_request(self):
        current=dict(self.player,fullscreen=0)
        requested=True
        changes=[]
        def ipc(state,action,key,*args):
            nonlocal requested
            if action=='get_property':return requested
            changes.append(args[0])
            if requested!=args[0]:current['fullscreen']=2 if args[0] else 0
            requested=args[0]
        with patch.object(layout,'hypr',side_effect=lambda *args:json.dumps([current])), \
                patch.object(layout,'socket_for',return_value='player.sock'), \
                patch.object(layout,'ipc',side_effect=ipc):
            self.assertEqual(layout.restore_transition_fullscreen(self.player)['fullscreen'],2)
            self.assertEqual(changes,[False,True])

    def test_cover_waits_through_missing_state_loading_and_geometry(self):
        request={'bounds':{'at':[100,0],'size':[300,900]}}
        player=dict(self.player,fullscreen=2)
        chat=dict(self.chat,at=[100,0],size=[300,900],**{'class':'newsboat-live-chat'})
        state={'player':player,'chat':chat}
        monitor={'specialWorkspace':{'name':'special:chatterino_chat'}}
        self.assertFalse(layout.chat_cover_ready(request,None,[player,chat],monitor,lambda pid:True))
        self.assertFalse(layout.chat_cover_ready(request,state,[player,chat],monitor,lambda pid:False))
        self.assertFalse(layout.chat_cover_ready(request,state,[player,dict(chat,at=[0,0])],monitor,lambda pid:True))
        self.assertFalse(layout.chat_cover_ready(request,state,[dict(player,fullscreen=0),chat],monitor,lambda pid:True))
        self.assertTrue(layout.chat_cover_ready(request,state,[player,chat],monitor,lambda pid:True))

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
                    if action=='get_property':return props.get(key)
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
                    self.assertAlmostEqual(props['video-margin-ratio-right'], .20)
                    self.assertTrue(layout.close([self.player, chat]))
                    self.assertEqual(props['video-margin-ratio-right'],0)
