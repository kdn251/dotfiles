import fcntl
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('playback', Path(__file__).resolve().parents[1]/'scripts/stream-playback-url.py')
playback=importlib.util.module_from_spec(spec)
spec.loader.exec_module(playback)

class PrefetchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        best=patch('stream_hls.resolve_best',side_effect=lambda url, service: url)
        best.start();self.addCleanup(best.stop)
        root=patch.object(playback,'root',return_value=self.root);root.start();self.addCleanup(root.stop)

    def test_selection_reuses_prefetch_for_each_platform(self):
        for service in ('Kick','YouTube','Rumble'):
            response={'url':'https://example.test/live','icon':'/tmp/avatar','title':'Title'}
            with patch.object(playback.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(response),'')) as run:
                self.assertEqual(playback.resolve(service,'https://example.test/'+service,prefetch=True),response)
                self.assertEqual(playback.resolve(service,'https://example.test/'+service),response)
                run.assert_called_once()
        for file in self.root.glob('*.json'):
            self.assertEqual(file.stat().st_mode & 0o777,0o600)

    def test_expired_result_is_refetched(self):
        result=subprocess.CompletedProcess([],0,'{"url":"https://example.test/live"}','')
        with patch.object(playback.subprocess,'run',return_value=result) as run, patch.object(playback.time,'time',return_value=100):
            playback.resolve('Kick','https://kick.com/example')
            with patch.object(playback.time,'time',return_value=121):
                playback.resolve('Kick','https://kick.com/example')
            self.assertEqual(run.call_count,2)

    def test_busy_prefetch_does_not_block_explicit_selection(self):
        with (self.root/'prefetch.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with patch.object(playback.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"url":"https://example.test/live"}','')) as run:
                self.assertIsNone(playback.resolve('Kick','https://kick.com/example',prefetch=True))
                run.assert_not_called()
                self.assertIsNotNone(playback.resolve('Kick','https://kick.com/selected'))
                run.assert_called_once()

    def test_failed_lookup_not_cached(self):
        with patch.object(playback.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','offline')):
            with self.assertRaises(ValueError):playback.resolve('Kick','https://kick.com/example')
        self.assertEqual(list(self.root.glob('*.json')),[])
