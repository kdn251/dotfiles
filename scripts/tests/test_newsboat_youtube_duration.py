import json
import unittest
from unittest.mock import patch
import newsboat_youtube_duration as fast
import newsboat_queue_time as timing

VIDEO='abcdefghijk'
URL='https://www.youtube.com/watch?v='+VIDEO

def page(video=VIDEO,seconds='123',status='OK',live=False):
    return 'var ytInitialPlayerResponse = '+json.dumps({'videoDetails':{'videoId':video,'lengthSeconds':seconds,'isLive':live},'playabilityStatus':{'status':status}})+';'

class FastDurationTests(unittest.TestCase):
    def test_parse_accepts_only_matching_playable_recorded_video(self):
        self.assertEqual(fast.parse_duration(page(),VIDEO),123)
        for text in (page(video='other'),page(seconds='bad'),page(seconds='-1'),page(status='LOGIN_REQUIRED'),page(live=True),'consent page','ytInitialPlayerResponse = {broken}'):
            self.assertEqual(fast.parse_duration(text,VIDEO),0)

    def test_success_skips_ytdlp_and_failure_falls_back(self):
        with patch.object(timing.media,'playback_file',return_value=None),patch.object(fast,'fetch',return_value=123) as fetch,patch.object(timing.subprocess,'run') as run:
            self.assertEqual(timing.resolve_duration(URL),123)
            fetch.assert_called_once_with(VIDEO);run.assert_not_called()
            fetch.return_value=0;run.return_value.returncode=0;run.return_value.stdout='456'
            self.assertEqual(timing.resolve_duration(URL),456)
            self.assertIn('--skip-download',run.call_args.args[0])
