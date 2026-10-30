import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('browser', Path(__file__).resolve().parents[1]/'scripts/stream-open-browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)

class BrowserTests(unittest.TestCase):
    def test_all_platforms_open_public_page_as_separate_argument(self):
        with patch.object(browser.shutil, 'which', return_value='/usr/bin/brave'), \
                patch.object(browser.subprocess, 'Popen') as launch:
            for url in ('https://www.twitch.tv/example', 'https://kick.com/example',
                        'https://www.youtube.com/watch?v=abcdefghijk',
                        'https://rumble.com/v12345-example.html'):
                self.assertTrue(browser.open_page(url))
                self.assertEqual(launch.call_args.args[0], ['/usr/bin/brave', '--new-tab', url])

    def test_media_urls_and_other_schemes_are_not_opened(self):
        for url in ('file:///tmp/video', 'https://cdn.example/live.m3u8',
                    'https://kick.com/live.m3u8', 'https://twitch.tv@evil.example/test'):
            self.assertFalse(browser.valid_page(url))
