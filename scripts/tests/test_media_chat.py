import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('media_chat',SCRIPTS/'media-chat.py')
chat=importlib.util.module_from_spec(spec);spec.loader.exec_module(chat)
URL='https://www.youtube.com/watch?v=abc123DEF45'

class ChatTests(unittest.TestCase):
    def setUp(self):
        toggle=patch.object(chat.fullscreen_chat,'toggle_workspace')
        self.toggle=toggle.start();self.addCleanup(toggle.stop)
        retire=patch.object(chat.fullscreen_chat,'retire_chat_window')
        self.retire=retire.start();self.addCleanup(retire.stop)
        for method in ('begin', 'close', 'prepare_chat_window'):
            mock = patch.object(chat.fullscreen_chat, method, return_value=False)
            mock.start(); self.addCleanup(mock.stop)

    def test_late_handoff_does_not_show_windowed_chat(self):
        import json
        with patch.object(chat.sys,'argv',['media-chat.py','--handoff']), \
             patch.object(chat.fullscreen_chat,'read',return_value=None), \
             patch.object(chat,'hypr',return_value=json.dumps([{'class':'mpv','fullscreen':0}])):
            chat.show_workspace()
        self.toggle.assert_not_called()

    def test_exit_intent_blocks_chat_before_fullscreen_ack(self):
        with patch.object(chat.sys,'argv',['media-chat.py','--handoff']), \
             patch.object(chat.fullscreen_chat,'read',return_value={'exiting':True}), \
             patch.object(chat,'hypr') as query:
            chat.show_workspace()
        query.assert_not_called()
        self.toggle.assert_not_called()

    def test_theater_reveal_focuses_video_after_showing_chat(self):
        events=[]
        self.toggle.side_effect=lambda:events.append('show')
        def hypr(*args):
            if args == ('-j','clients'): return '[]'
            if args == ('-j','monitors'): return '[{"focused":true,"specialWorkspace":{}}]'
            events.append('show')
            return 'ok'
        with patch.object(chat.fullscreen_chat,'begin',return_value=True), \
                patch.object(chat.fullscreen_chat,'focus_player',side_effect=lambda:events.append('focus video')), \
                patch.object(chat,'hypr',side_effect=hypr):
            chat.show_workspace()
        self.assertEqual(events,['show','focus video'])

    def test_downloaded_player_uses_original_youtube_url(self):
        with patch.object(Path,'read_bytes',return_value=b'NEWSBOAT_MEDIA_URL='+URL.encode()+b'\0'):
            self.assertEqual(chat.video_url([{'class':'mpv','pid':123,'address':'a'}],'a'),URL)
    def test_focused_twitch_player_keeps_twitch_chat(self):
        def env(path):
            return b'NEWSBOAT_MEDIA_URL=https://twitch.tv/someone\0' if '/123/' in str(path) else b'NEWSBOAT_MEDIA_URL='+URL.encode()+b'\0'
        with patch.object(Path,'read_bytes',env):
            self.assertIsNone(chat.video_url([{'class':'mpv','pid':123,'address':'a'},{'class':'mpv','pid':124,'address':'b'}],'a'))
    def test_repeated_shortcut_toggles_existing_panel(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state';state.write_text('{"url":"'+URL+'"}')
            with patch.object(chat,'STATE',state),patch.object(chat,'video_url',return_value=URL),patch.object(chat,'hypr',side_effect=['[{"class":"newsboat-youtube-comments"}]','{}','ok']) as hypr,patch.object(chat.subprocess,'Popen') as spawn,patch.object(chat.subprocess,'run'):
                chat.main()
                self.toggle.assert_called_once_with()
                spawn.assert_not_called()
    def test_switching_closes_other_panel_without_hiding_current_workspace(self):
        import json
        clients=[{'class':chat.CLASS,'address':'yt'},
                 {'class':'com.chatterino.chatterino','address':'twitch'}]
        for url,closed in ((None,'yt'),(URL,'twitch')):
            with self.subTest(url=url),tempfile.TemporaryDirectory() as d:
                state=Path(d)/'state';state.write_text(json.dumps({'url':URL}))
                def respond(*args):
                    if args==('-j','clients'):return json.dumps(clients)
                    if args==('-j','activewindow'):return '{}'
                    if args==('-j','monitors'):return json.dumps([{'focused':True,'specialWorkspace':{'name':'special:'+chat.WORKSPACE}}])
                    return 'ok'
                with patch.object(chat,'STATE',state),patch.object(chat,'video_url',return_value=url),patch.object(chat,'hypr',side_effect=respond) as hypr,patch.object(chat.subprocess,'Popen') as spawn,patch.object(chat.subprocess,'run'):
                    chat.main()
                    self.retire.assert_any_call(closed)
                    self.assertFalse(any(c.args[:2]==('dispatch','togglespecialworkspace') for c in hypr.call_args_list))
                    spawn.assert_not_called()

    def test_preload_stays_hidden_and_reuses_loaded_panel(self):
        import json
        player={'class':'mpv','pid':123,'address':'player'}
        panel={'class':chat.CLASS,'address':'comments','pid':456}
        for already_loaded in (False,True):
            with self.subTest(already_loaded=already_loaded),tempfile.TemporaryDirectory() as d:
                state=Path(d)/'state';state.write_text(json.dumps({'url':URL}))
                responses=[json.dumps([player,panel] if already_loaded else [player])]
                if not already_loaded:responses.append(json.dumps([player,panel]))
                with patch.object(chat,'STATE',state),patch.object(chat.sys,'argv',['media-chat','--preload','123']),                         patch.object(chat,'video_url',return_value=URL),patch.object(chat,'live_target',return_value=None),                         patch.object(chat,'hypr',side_effect=responses) as hypr,patch.object(chat,'show_workspace') as show,                         patch.object(chat.subprocess,'Popen') as spawn:
                    spawn.return_value.pid=456
                    chat.main()
                    show.assert_not_called()
                    self.assertEqual(spawn.call_count,0 if already_loaded else 1)
                    self.assertTrue(all(c.args==('-j','clients') for c in hypr.call_args_list))

    def test_reused_player_comments_follow_current_ipc_url(self):
        new_url='https://www.youtube.com/watch?v=xyz123DEF45'
        with patch.object(Path,'read_bytes',return_value=b'NEWSBOAT_MEDIA_URL='+URL.encode()+b'\0'),                 patch.object(chat.fullscreen_chat,'socket_for',return_value='/tmp/player'),                 patch.object(chat.fullscreen_chat,'ipc',return_value=new_url):
            self.assertEqual(chat.video_url([{'class':'mpv','pid':123,'address':'a'}],'a'),new_url)

    def test_new_live_chat_waits_for_replacement_pid_not_closing_window(self):
        import json
        player={'class':'mpv','pid':123,'address':'player'}
        old={'class':chat.LIVE_CLASS,'pid':111,'address':'old',
             'workspace':{'name':'special:media_chat_closing'}}
        new={'class':chat.LIVE_CLASS,'pid':222,'address':'new',
             'workspace':{'name':'special:chatterino_chat'}}
        responses=[json.dumps([player,old]),'{}',json.dumps([player,old]),json.dumps([player,new])]
        with tempfile.TemporaryDirectory() as d,patch.object(chat,'STATE',Path(d)/'state'), \
                patch.object(chat.sys,'argv',['media-chat','--handoff']), \
                patch.object(chat,'live_target',return_value={'url':'https://kick.com/popout/nickwhite/chat','title':'Kick live chat'}), \
                patch.object(chat,'hypr',side_effect=responses),patch.object(chat,'close_panels',return_value=False), \
                patch.object(chat.subprocess,'Popen') as spawn,patch.object(chat,'show_workspace') as show, \
                patch.object(chat.time,'sleep') as wait:
            spawn.return_value.pid=222
            chat.main()
            wait.assert_called_once_with(.1)
            show.assert_called_once()
