import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('opener', SCRIPTS/'newsboat-open.py')
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class RoutingTests(unittest.TestCase):
    def test_videos_and_twitch_channels_use_the_existing_player(self):
        for url in ['https://www.youtube.com/watch?v=abc123DEF45',
                    'https://youtu.be/abc123DEF45', 'https://www.twitch.tv/shroud',
                    'https://twitch.tv/creator_123/?ref=newsboat',
                    'https://m.twitch.tv/creator', 'https://twitch.tv/videos/1234567890']:
            with self.subTest(url=url):
                self.assertEqual(opener.launcher_for(url), 'newsboat-play-video.sh')

    def test_nonvideo_links_stay_in_browser(self):
        for url in ['https://reddit.com/r/linux', 'https://twitch.tv/directory',
                    'https://twitch.tv/', 'https://youtube.com/@creator',
                    'https://twitch.tv.evil.example/shroud',
                    'https://example.com/?url=https://twitch.tv/shroud']:
            with self.subTest(url=url):
                self.assertEqual(opener.launcher_for(url), 'newsboat-brave-app.sh')


if __name__ == '__main__':
    unittest.main()
