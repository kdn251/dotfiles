from contextlib import closing
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import newsboat_download_cleanup as cleanup
import newsboat_download_status as status
import newsboat_media as media


class CleanupTests(unittest.TestCase):
    def test_only_watched_unchanged_unprotected_closed_files_are_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); videos=root/'videos';videos.mkdir()
            with patch.multiple(media,ROOT=videos,CACHE=root/'cache',STATE=root/'downloads'), patch.object(cleanup,'STATE',root/'state'), patch.object(media,'rebuild_unlocked'), patch.object(cleanup,'player_paths',return_value=set()) as players:
                url='https://www.youtube.com/watch?v=abc123DEF45'
                video=videos/'Example [abc123DEF45].mp4';video.write_bytes(b'video')
                self.assertFalse(cleanup.record(video,url,.1))
                self.assertEqual(cleanup.cleanup([],7,now=time.time()+8*86400),[])
                self.assertTrue(cleanup.record(video,url,.95))
                now=time.time()+8*86400
                self.assertEqual(cleanup.cleanup([url],7,now),[])
                players.return_value={video.resolve()}
                self.assertEqual(cleanup.cleanup([],7,now),[])
                players.return_value=set()
                video.write_bytes(b'redownloaded')
                self.assertEqual(cleanup.cleanup([],7,now),[])
                cleanup.record(video,url,1)
                self.assertEqual(cleanup.cleanup([],7,time.time()+1),[])
                self.assertEqual(cleanup.cleanup([],7,now),[str(video)])
                self.assertFalse(video.exists())


class DownloadStatusTests(unittest.TestCase):
    def test_live_progress_failure_and_deleted_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'downloads';state.mkdir()
            url='https://www.youtube.com/watch?v=abc123DEF45'
            job=dict(url=url,status='downloading',percent=42,pid=os.getpid(),process_start=media.start_time(os.getpid()))
            path=state/'job.json';path.write_text(json.dumps(job))
            status.publish(state)
            target=root/'download-status.tsv'
            self.assertIn('↓ 42%',target.read_text())
            job['status']='failed';path.write_text(json.dumps(job));status.publish(state)
            self.assertIn('✕',target.read_text())
            job.update(status='done',files=[str(root/'missing.mp4')]);path.write_text(json.dumps(job));status.publish(state)
            self.assertEqual(target.read_text(),'')
