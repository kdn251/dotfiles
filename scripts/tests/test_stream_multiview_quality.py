import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from stream_multiview_quality import hls_qualities

class QualityTests(unittest.TestCase):
    def test_background_uses_480p_and_active_uses_best(self):
        manifest='#EXTM3U\n'+''.join(f'#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION={h*16//9}x{h}\n{h}.m3u8\n' for h in (1080,360,720,480))
        self.assertEqual(hls_qualities(manifest,'https://example.com/master.m3u8'),('https://example.com/1080.m3u8','https://example.com/480.m3u8'))
    def test_no_low_rendition_uses_lowest_available(self):
        manifest='#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=1920x1080\n1080.m3u8\n#EXT-X-STREAM-INF:RESOLUTION=1280x720\n720.m3u8\n'
        self.assertTrue(hls_qualities(manifest,'https://example.com/master')[1].endswith('720.m3u8'))
    def test_external_audio_and_single_rendition_remain_playable(self):
        url='https://example.com/master'
        for manifest in ('#EXTM3U\n#EXTINF:2\nsegment.ts', '#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,URI="audio.m3u8"\n#EXT-X-STREAM-INF:RESOLUTION=1920x1080\nvideo.m3u8'):
            self.assertEqual(hls_qualities(manifest,url),(url,url))
