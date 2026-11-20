import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('player_info', SCRIPTS / 'newsboat-player-info.py')
info = importlib.util.module_from_spec(spec)
spec.loader.exec_module(info)


class PlayerTitleTests(unittest.TestCase):
    def test_queue_title_survives_missing_feed_item(self):
        url = 'https://www.youtube.com/watch?v=OXdGzv7aLh8'
        with patch('newsboat_queue.metadata', return_value={'title': url, 'source': ''}), patch(
            'newsboat_queue.entries', return_value=[{'url': url, 'title': 'Real video title', 'source': 'Creator'}]
        ):
            self.assertEqual(info.metadata(url)['title'], 'Real video title')
            self.assertEqual(info.metadata(url)['source'], 'Creator')

    def test_missing_title_does_not_replace_player_title_with_url(self):
        with patch('newsboat_queue.metadata', return_value={'title': 'https://example.com', 'source': ''}), patch(
            'newsboat_queue.entries', return_value=[]
        ):
            self.assertEqual(info.metadata('https://example.com')['title'], '')


if __name__ == '__main__':
    unittest.main()
