import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('quality', Path(__file__).parents[1] / 'scripts/live-stream-quality.py')
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


class QualityTests(unittest.TestCase):
    def test_master_playlist_handles_relative_urls_and_duplicate_resolutions(self):
        text = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=4000,RESOLUTION=1920x1080
high/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1500,RESOLUTION=1280x720
low/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500,RESOLUTION=1280x720
https://example.com/better.m3u8
'''
        self.assertEqual(quality.variants(text, 'https://example.com/master.m3u8'),
                         {1080: 'https://example.com/high/index.m3u8', 720: 'https://example.com/better.m3u8'})

    def test_quality_cycle_wraps_and_skips_unavailable_levels(self):
        levels = ['best', '720p', '360p']
        self.assertEqual(quality.next_quality('best', levels), '720p')
        self.assertEqual(quality.next_quality('720p', levels), '360p')
        self.assertEqual(quality.next_quality('360p', levels), 'best')
        self.assertEqual(quality.next_quality('480p', levels), 'best')

    def test_media_playlist_has_no_fake_quality_choices(self):
        self.assertEqual(quality.variants('#EXTM3U\n#EXTINF:2\nsegment.ts', 'https://example.com/live.m3u8'), {})
