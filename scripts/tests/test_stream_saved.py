import tempfile
import unittest
from pathlib import Path
from stream_saved import parse,save

class SavedTests(unittest.TestCase):
    def test_platforms_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            for text,service in [('@Somebody','Twitch'),('k/Example','Kick'),('y/Example','YouTube'),('r/Example','Rumble')]:
                self.assertEqual(parse(text)[0],service)
                self.assertTrue(save(text,directory)[1])
                self.assertFalse(save(text.lower(),directory)[1])
            self.assertEqual((Path(directory)/'kick_channels.tsv').read_text(),'example\thttps://kick.com/example\n')
    def test_invalid_and_video_urls(self):
        for text in ('','a b','https://example.com/user','https://www.youtube.com/watch?v=123','https://twitch.tv/videos/123'):
            with self.assertRaises(ValueError):parse(text)
