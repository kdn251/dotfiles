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
        for method in ('begin', 'close'):
            mock = patch.object(chat.fullscreen_chat, method, return_value=False)
            mock.start(); self.addCleanup(mock.stop)

    def test_theater_reveal_focuses_video_after_showing_chat(self):
        events=[]
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
                hypr.assert_called_with('dispatch','togglespecialworkspace','chatterino_chat')
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
                    hypr.assert_any_call('dispatch','movetoworkspacesilent','special:media_chat_closing,address:'+closed)
                    hypr.assert_any_call('dispatch','closewindow','address:'+closed)
                    self.assertFalse(any(c.args[:2]==('dispatch','togglespecialworkspace') for c in hypr.call_args_list))
                    spawn.assert_not_called()

    def test_preload_stays_hidden_and_reuses_loaded_panel(self):
        import json
        player={'class':'mpv','pid':123,'address':'player'}
        panel={'class':chat.CLASS,'address':'comments'}
        for already_loaded in (False,True):
            with self.subTest(already_loaded=already_loaded),tempfile.TemporaryDirectory() as d:
                state=Path(d)/'state';state.write_text(json.dumps({'url':URL}))
                responses=[json.dumps([player,panel] if already_loaded else [player])]
                if not already_loaded:responses.append(json.dumps([player,panel]))
                with patch.object(chat,'STATE',state),patch.object(chat.sys,'argv',['media-chat','--preload','123']),                         patch.object(chat,'video_url',return_value=URL),patch.object(chat,'live_target',return_value=None),                         patch.object(chat,'hypr',side_effect=responses) as hypr,patch.object(chat,'show_workspace') as show,                         patch.object(chat.subprocess,'Popen') as spawn:
                    chat.main()
                    show.assert_not_called()
                    self.assertEqual(spawn.call_count,0 if already_loaded else 1)
                    self.assertTrue(all(c.args==('-j','clients') for c in hypr.call_args_list))

    def test_reused_player_comments_follow_current_ipc_url(self):
        new_url='https://www.youtube.com/watch?v=xyz123DEF45'
        with patch.object(Path,'read_bytes',return_value=b'NEWSBOAT_MEDIA_URL='+URL.encode()+b'\0'),                 patch.object(chat.fullscreen_chat,'socket_for',return_value='/tmp/player'),                 patch.object(chat.fullscreen_chat,'ipc',return_value=new_url):
            self.assertEqual(chat.video_url([{'class':'mpv','pid':123,'address':'a'}],'a'),new_url)
