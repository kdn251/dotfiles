import unittest
from stream_hls import best_variant

class HlsTests(unittest.TestCase):
    def test_selects_highest_resolution_then_framerate(self):
        master='''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720,CODECS="avc1.4D401F,mp4a.40.2"
720.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080,FRAME-RATE=30
1080-30.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,FRAME-RATE=60
1080-60.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=100000
sound.m3u8
'''
        self.assertEqual(best_variant(master,'https://example.test/hls/master.m3u8'), 'https://example.test/hls/1080-60.m3u8')

    def test_keeps_master_for_external_tracks(self):
        for track in ('AUDIO','SUBTITLES'):
            master=f'''#EXTM3U
#EXT-X-MEDIA:TYPE={track},URI="track.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
video.m3u8
'''
            self.assertEqual(best_variant(master,'https://example.test/master.m3u8'),'https://example.test/master.m3u8')

    def test_media_playlist_or_malformed_variants_use_original(self):
        for manifest in ('not hls','#EXTM3U\n#EXTINF:2\nsegment.ts',
                         '#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=1920x1080,BANDWIDTH=bad\nvideo.m3u8'):
            self.assertEqual(best_variant(manifest,'https://example.test/master.m3u8'),'https://example.test/master.m3u8')
