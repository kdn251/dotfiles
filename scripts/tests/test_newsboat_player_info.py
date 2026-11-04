import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

spec=importlib.util.spec_from_file_location('info',Path(__file__).resolve().parents[1]/'scripts/newsboat-player-info.py')
info=importlib.util.module_from_spec(spec);spec.loader.exec_module(info)
URL='https://www.youtube.com/watch?v=abcdefghijk'

class InfoTests(unittest.TestCase):
    def test_local_playback_overrides_download_job_and_stale_job_is_not_downloading(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(info,'STATE',Path(tmp)),patch.object(info,'CACHE',Path(tmp)):
            path=Path(tmp)/(hashlib.sha256(URL.encode()).hexdigest()[:24]+'.json')
            path.write_text(json.dumps(dict(status='downloading',percent=42,pid=123,process_start='456')))
            with patch.object(info,'start_time',return_value='456'):
                self.assertEqual(info.status(URL,'/video.mp4'),'Local')
                self.assertEqual(info.status('https://youtu.be/abcdefghijk','https://media/video'),'Downloading 42%')
            with patch.object(info,'start_time',return_value=None):
                self.assertEqual(info.status(URL,'https://media/video'),'Streaming')

    def test_chapters_use_download_metadata_and_reuse_cache_offline(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(info,'STATE',Path(tmp)),patch.object(info.Path,'home',return_value=Path(tmp)):
            path=Path(tmp)/(hashlib.sha256(URL.encode()).hexdigest()[:24]+'.json')
            path.write_text(json.dumps({'chapters':[{'start_time':60,'title':'Second'},{'start_time':0,'title':'Intro'}]}))
            with patch.object(info.subprocess,'run') as run:
                self.assertEqual(info.chapters(URL),[{'time':0,'title':'Intro'},{'time':60,'title':'Second'}])
                path.unlink()
                self.assertEqual(info.chapters(URL)[1]['title'],'Second')
                run.assert_not_called()

    def test_video_with_no_chapters_is_cached_without_inventing_chapters(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(info,'STATE',Path(tmp)),patch.object(info.Path,'home',return_value=Path(tmp)),patch.object(info.subprocess,'run',return_value=Mock(stdout='null')) as run:
            self.assertEqual(info.chapters(URL),[])
            self.assertEqual(info.chapters(URL),[])
            run.assert_called_once()
