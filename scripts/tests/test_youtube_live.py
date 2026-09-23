import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
spec = importlib.util.spec_from_file_location('youtube_live', Path(__file__).parents[1] / 'scripts/youtube-live.py')
youtube = importlib.util.module_from_spec(spec)
spec.loader.exec_module(youtube)


class YouTubeLiveTests(unittest.TestCase):
    def test_selects_live_broadcast_among_replays_and_scheduled(self):
        entries = [{'id': 'aaaaaaaaaaa', 'live_status': 'was_live'},
                   {'id': 'bbbbbbbbbbb', 'live_status': 'is_upcoming'},
                   {'id': 'ccccccccccc', 'live_status': 'is_live', 'title': 'Live title'}]
        self.assertEqual(youtube.resolve({'entries': entries}), {
            'url': 'https://www.youtube.com/watch?v=ccccccccccc', 'title': 'Live title'})

    def test_offline_and_unknown_status_are_not_live(self):
        for status in ['was_live', 'post_live', 'not_live', 'is_upcoming', None]:
            with self.subTest(status=status), self.assertRaises(youtube.OfflineError):
                youtube.resolve({'entries': [{'id': 'aaaaaaaaaaa', 'live_status': status}]})

    def test_bad_response_is_not_reported_as_offline(self):
        with self.assertRaisesRegex(ValueError, 'stream listing'):
            youtube.resolve({'error': 'unavailable'})

    def test_requires_channel_url(self):
        with self.assertRaisesRegex(ValueError, 'channel URL'):
            youtube.fetch('https://example.com/@someone')


if __name__ == '__main__':
    unittest.main()
