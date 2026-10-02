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
