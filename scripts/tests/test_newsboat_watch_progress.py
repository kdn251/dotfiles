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

    def test_resume_tracks_identity_and_migrates_old_percentage_records(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch.object(progress,'STATE',root),patch.object(progress.media,'STATE',root/'downloads'),patch.dict(os.environ,NEWSBOAT_CACHE=str(root/'absent')):
                url='https://www.youtube.com/watch?v=abc123DEF45'
                with sqlite3.connect(root/'watch-progress.db') as db:
                    db.execute('CREATE TABLE progress(identity TEXT PRIMARY KEY,url TEXT,fraction REAL,updated REAL)')
                    db.execute('INSERT INTO progress VALUES (?,?,?,?)',('youtube:abc123DEF45',url,.4,0))
                self.assertEqual(progress.resume_position(url,200),80)
                progress.record(url,73,200)
                self.assertEqual(progress.resume_position('https://youtu.be/abc123DEF45',200),73)
                self.assertEqual(progress.resume_position(url,50),49.5)
                progress.record(url,200,200)
                self.assertEqual(progress.resume_position(url,200),0)
                self.assertEqual(progress.resume_position('https://www.twitch.tv/streamer',200),0)
