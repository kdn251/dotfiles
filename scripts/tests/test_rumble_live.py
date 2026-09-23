import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
import time
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

spec = importlib.util.spec_from_file_location('rumble_live', Path(__file__).parents[1] / 'scripts/rumble-live.py')
rumble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rumble)
CHANNEL = 'https://rumble.com/c/Tectone'


def page(items):
    return '<script type="application/json">' + json.dumps({'items': items}) + '</script>'


def video(**changes):
    item = {'by': {'url': CHANNEL}, 'live': True, 'live_placeholder': False,
            'title': 'A stream title', 'videos': [{'type': 'hls', 'url': 'https://rumble.com/live/test.m3u8'}]}
    return item | changes


class RumbleTests(unittest.TestCase):
    def test_live_stream_after_replay(self):
        result = rumble.resolve(page([video(live=False), video()]), CHANNEL)
        self.assertEqual(result['title'], 'A stream title')
        self.assertEqual(result['url'], 'https://rumble.com/live/test.m3u8')

    def test_never_play_replays_scheduled_or_other_channels(self):
        for item in [video(live=False), video(live_placeholder=True),
                     video(by={'url': 'https://rumble.com/c/SomeoneElse'})]:
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, 'offline'):
                rumble.resolve(page([item]), CHANNEL)

    def test_live_cache_transitions_and_network_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            channels, cache = root / 'channels', root / 'live.json'
            channels.write_text(f'Tectone {CHANNEL}\n')
            rumble.update_live_list(channels, cache, lambda _: {'url': 'https://rumble.com/live.m3u8', 'title': 'Live'})
            self.assertIn('Tectone', json.loads(cache.read_text()))

            def unavailable(_):
                raise TimeoutError('network unavailable')

            rumble.update_live_list(channels, cache, unavailable)
            self.assertIn('Tectone', json.loads(cache.read_text()))
            stale = json.loads(cache.read_text())
            stale['Tectone']['checked_at'] = time.time() - 901
            cache.write_text(json.dumps(stale))
            rumble.update_live_list(channels, cache, unavailable)
            self.assertEqual(json.loads(cache.read_text()), {})
            rumble.update_live_list(channels, cache, lambda _: {'title': 'Live'})

            def offline(_):
                raise rumble.OfflineError('offline')

            rumble.update_live_list(channels, cache, offline)
            self.assertEqual(json.loads(cache.read_text()), {})

    def test_unplayable_live_and_changed_layout(self):
        with self.assertRaisesRegex(ValueError, 'no public playable'):
            rumble.resolve(page([video(videos=[])]), CHANNEL)
        with self.assertRaisesRegex(ValueError, 'page format'):
            rumble.resolve('<html>Unavailable</html>', CHANNEL)


if __name__ == '__main__':
    unittest.main()
