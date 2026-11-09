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
            'url': 'https://www.youtube.com/watch?v=ccccccccccc', 'title': 'Live title',
            'chat_url': 'https://www.youtube.com/live_chat?v=ccccccccccc&is_popout=1'})

    def test_offline_and_unknown_status_are_not_live(self):
        for status in ['was_live', 'post_live', 'not_live', 'is_upcoming', None]:
            with self.subTest(status=status), self.assertRaises(youtube.OfflineError):
                youtube.resolve({'entries': [{'id': 'aaaaaaaaaaa', 'live_status': status}]})

    def test_bad_response_is_not_reported_as_offline(self):
        with self.assertRaisesRegex(ValueError, 'stream listing'):
            youtube.resolve({'error': 'unavailable'})

    def test_playback_selects_one_video_and_audio_instead_of_full_master(self):
        details={'formats':[
            {'height':720,'protocol':'m3u8_native','url':'https://example.com/720','acodec':'none'},
            {'height':1080,'protocol':'m3u8_native','url':'https://example.com/1080','acodec':'none'},
            {'height':2160,'protocol':'m3u8_native','url':'https://example.com/4k','acodec':'none'},
            {'vcodec':'none','protocol':'m3u8_native','url':'https://example.com/low-audio','source_preference':0},
            {'vcodec':'none','protocol':'m3u8_native','url':'https://example.com/audio','source_preference':1}]}
        selected=youtube.playback_manifest(details)
        self.assertTrue(selected.startswith('edl://'))
        self.assertIn('https://example.com/1080',selected)
        self.assertIn('https://example.com/audio',selected)
        self.assertNotIn('https://example.com/low-audio',selected)
        self.assertNotIn('https://example.com/720',selected)
        self.assertNotIn('https://example.com/4k',selected)
        self.assertIsNone(youtube.playback_manifest({'formats':[]}))
        self.assertIsNone(youtube.playback_manifest({'formats':details['formats'][:2]}))

    def test_cached_manifest_must_be_recent_and_match_channel(self):
        import json
        from unittest.mock import patch
        stream={'channel':'https://www.youtube.com/@Test','checked_at':100,'playback_resolved_at':100,'playback_url':'https://example.com/master'}
        with patch.object(Path,'read_text',return_value=json.dumps({'Test':stream})):
            self.assertEqual(youtube.recent_stream(stream['channel'],101),stream)
            self.assertIsNone(youtube.recent_stream(stream['channel'],121))
            stream['checked_at']=120
        with patch.object(Path,'read_text',return_value=json.dumps({'Test':stream})):
            self.assertIsNone(youtube.recent_stream(stream['channel'],121))
            self.assertIsNone(youtube.recent_stream('https://www.youtube.com/@Other',101))

    def test_requires_channel_url(self):
        with self.assertRaisesRegex(ValueError, 'channel URL'):
            youtube.fetch('https://example.com/@someone')


if __name__ == '__main__':
    unittest.main()
