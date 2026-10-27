import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import newsboat_autoplay as autoplay

class PlaylistPriority(unittest.TestCase):
    def test_playlist_wins_even_if_current_queued_and_stops_at_end(self):
        urls=['https://www.youtube.com/watch?v='+str(i)*11 for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            context=Path(tmp)/'playlist.json'
            context.write_text(json.dumps({'rows':[{'url':u} for u in urls[:2]]}))
            queued=[{'url':urls[0],'queue_token':'first'},{'url':urls[2],'queue_token':'other'}]
            with patch.dict(os.environ,NEWSBOAT_PLAYLIST_CONTEXT=str(context),NEWSBOAT_QUEUE_PLAYBACK='0'), patch('newsboat_queue.entries',return_value=queued):
                self.assertEqual(autoplay.plan(urls[0])['next']['url'],urls[1])
                self.assertIsNone(autoplay.plan(urls[1])['next'])
                self.assertFalse(autoplay.plan(urls[0]).get('queue',False))
                with patch.dict(os.environ,NEWSBOAT_QUEUE_PLAYBACK='1'), patch('newsboat_queue.navigation',return_value=(queued[1],None,queued[1])):
                    self.assertEqual(autoplay.plan(urls[0])['next']['url'],urls[2])

if __name__=='__main__':unittest.main()
