import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

spec=importlib.util.spec_from_file_location('stream_url',Path(__file__).resolve().parents[1]/'scripts/twitch-stream-url.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

class StreamURLTests(unittest.TestCase):
    def test_prefetch_reuse_expiry_and_quality(self):
        streams={k:{'url':'https://example.test/'+k} for k in ('160p30','480p30','worst','best')}
        response=Mock(returncode=0,stdout=json.dumps({'streams':streams}))
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,XDG_RUNTIME_DIR=root), patch.object(helper.subprocess,'run',return_value=response) as run:
            first=helper.resolve('example',prefetch=True)
            self.assertTrue(first['low'].endswith('480p30'))
            self.assertTrue(first['best'].endswith('best'))
            self.assertEqual(helper.resolve('example'),first)
            self.assertEqual(run.call_count,1)
            with patch.object(helper.time,'time',return_value=first['created']+61):helper.resolve('example')
            self.assertEqual(run.call_count,2)
            self.assertEqual((Path(root)/'twitch-stream-urls/example.json').stat().st_mode&0o777,0o600)

    def test_bad_name_and_failed_resolution_not_cached(self):
        with self.assertRaises(ValueError):helper.resolve('../bad')
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,XDG_RUNTIME_DIR=root), patch.object(helper.subprocess,'run',return_value=Mock(returncode=1)):
            with self.assertRaises(ValueError):helper.resolve('offline')
            self.assertFalse((Path(root)/'twitch-stream-urls/offline.json').exists())

if __name__=='__main__':unittest.main()
