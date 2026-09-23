import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
progress = importlib.import_module('newsboat_watch_progress')


class WatchProgressTests(unittest.TestCase):
    def test_resume_percentage_completion_and_rewind(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(progress, 'STATE', root), patch.object(progress.media, 'STATE', root/'downloads'), patch.dict(os.environ, NEWSBOAT_CACHE=str(root/'absent')):
                url = 'https://www.youtube.com/watch?v=abc123DEF45'
                target = root/'download-status.tsv.watched'
                self.assertTrue(progress.record(url, 72, 100))
                self.assertIn('\t72%\n', target.read_text())
                self.assertTrue(progress.record(url, 95, 100))
                self.assertIn('\t100%\n', target.read_text())
                progress.record(url, 10, 100)
                self.assertIn('\t10%\n', target.read_text())
                self.assertFalse(progress.record(url, 1, 0))
                self.assertFalse(progress.record(url, float('nan'), 100))
                self.assertIn('\t10%\n', target.read_text())
