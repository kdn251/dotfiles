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
            with patch.object(chat,'STATE',state),patch.object(chat,'video_url',return_value=URL),patch.object(chat,'hypr',side_effect=['[{"class":"newsboat-youtube-comments"}]','{}','ok']) as hypr,patch.object(chat.subprocess,'Popen') as spawn:
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
                with patch.object(chat,'STATE',state),patch.object(chat,'video_url',return_value=url),patch.object(chat,'hypr',side_effect=respond) as hypr,patch.object(chat.subprocess,'Popen') as spawn:
                    chat.main()
                    hypr.assert_any_call('dispatch','movetoworkspacesilent','special:media_chat_closing,address:'+closed)
                    hypr.assert_any_call('dispatch','closewindow','address:'+closed)
                    self.assertFalse(any(c.args[:2]==('dispatch','togglespecialworkspace') for c in hypr.call_args_list))
                    spawn.assert_not_called()
