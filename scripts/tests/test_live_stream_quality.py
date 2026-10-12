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

    def test_kick_quality_reloads_same_player_with_kick_referrer(self):
        import json
        import tempfile
        from unittest.mock import patch, MagicMock
        manifest=b'#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=1920x1080,BANDWIDTH=4000\nhigh.m3u8\n#EXT-X-STREAM-INF:RESOLUTION=1280x720,BANDWIDTH=2000\nlow.m3u8\n'
        with tempfile.TemporaryDirectory() as folder:
            context=Path(folder)/'player.json'
            context.write_text(json.dumps(dict(url='https://example.com/master.m3u8',quality='best',title='Kick title')))
            response=MagicMock();response.__enter__.return_value=response
            response.read.return_value=manifest;response.url='https://example.com/master.m3u8'
            with patch.object(quality,'urlopen',return_value=response) as fetch, patch.object(quality,'ipc',return_value=False) as ipc, patch.object(quality.subprocess,'run'):
                quality.cycle('kick',Path('/tmp/test-kick-ipc'),context)
                self.assertEqual(fetch.call_args.args[0].get_header('Referer'),'https://kick.com/')
                self.assertEqual(ipc.call_args_list[1].args[1],['loadfile','https://example.com/low.m3u8','replace',0,{'pause':'no'}])
                self.assertEqual(json.loads(context.read_text())['quality'],'720p')
