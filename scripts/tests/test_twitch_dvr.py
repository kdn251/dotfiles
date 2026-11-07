import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('dvr',Path(__file__).resolve().parents[1]/'scripts/twitch-dvr.py')
dvr=importlib.util.module_from_spec(spec);spec.loader.exec_module(dvr)
class SnapshotTests(unittest.TestCase):
    def test_snapshot_keeps_segments_and_resolves_keys_without_downloading_video(self):
        text='#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n#EXTINF:10.0,\nfirst.ts\n#EXTINF:9.5,\n/second.ts\n'
        result,duration=dvr.snapshot(text,'https://example.org/vod/index.m3u8?sig=test')
        self.assertEqual(duration,19.5)
        self.assertIn('URI="https://example.org/vod/key.bin"',result)
        self.assertIn('https://example.org/vod/first.ts',result)
        self.assertIn('https://example.org/second.ts',result)
        self.assertNotIn('PLAYLIST-TYPE:EVENT',result)
        self.assertTrue(result.endswith('#EXT-X-ENDLIST\n'))
        self.assertEqual(dvr.snapshot(result,'https://example.org/vod/index.m3u8')[0],result)
