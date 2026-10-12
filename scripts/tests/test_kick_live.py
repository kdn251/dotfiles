import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from stream_live_cache import update_live_list

spec=importlib.util.spec_from_file_location('kick',Path(__file__).parents[1]/'scripts/kick-live.py')
kick=importlib.util.module_from_spec(spec);spec.loader.exec_module(kick)

class KickTests(unittest.TestCase):
 def test_offline_playback_url_is_not_live(self):
  with self.assertRaises(kick.OfflineError):
   kick.resolve({'livestream':None,'playback_url':'https://example.com/old.m3u8'})
  with self.assertRaises(kick.OfflineError):
   kick.resolve({'livestream':{'is_live':False},'playback_url':'https://example.com/old.m3u8'})
 def test_live_title_and_stream(self):
  self.assertEqual(kick.resolve({'livestream':{'is_live':True,'session_title':'Live test'},'playback_url':'https://example.com/live.m3u8'}),{'url':'https://example.com/live.m3u8','title':'Live test'})
 def test_malformed_status_is_not_reported_offline(self):
  for data in ({'error':'rate limited'},{'livestream':{}},{'livestream':{'is_live':True}}):
   with self.assertRaises(ValueError) as error:kick.resolve(data)
   self.assertNotIsInstance(error.exception,kick.OfflineError)
 def test_live_cache_removes_offline_but_keeps_recent_network_failure(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);channels=root/'channels';cache=root/'cache'
   channels.write_text('nickwhite https://kick.com/nickwhite\n')
   update_live_list(channels,cache,lambda _:dict(url='https://example.com/live.m3u8',title='Test',icon='avatar.png'))
   self.assertIn('nickwhite',json.loads(cache.read_text()))
   with patch('stream_live_cache.sys.stderr'):
    update_live_list(channels,cache,lambda _:(_ for _ in ()).throw(OSError('network')))
   self.assertIn('nickwhite',json.loads(cache.read_text()))
   update_live_list(channels,cache,lambda _:(_ for _ in ()).throw(kick.OfflineError('offline')))
   self.assertEqual(json.loads(cache.read_text()),{})
