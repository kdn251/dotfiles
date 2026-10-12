import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from stream_live_cache import menu,stream_details
from test_kick_live import kick
from test_rumble_live import rumble,page,video,CHANNEL

class MenuDetailsTests(unittest.TestCase):
    def test_counts_and_optional_categories(self):
        self.assertEqual(stream_details({'category':'Gaming','viewer_count':6012}),'— Gaming · 6.0k')
        self.assertEqual(stream_details({'viewer_count':0}),'— 0')
        self.assertEqual(stream_details({}),'')
        self.assertEqual(stream_details({'category':'a\tb\nc'}),'— a b c')
    def test_service_metadata(self):
        result=kick.resolve({'livestream':{'is_live':True,'playback_url':'https://example.com/live.m3u8','viewer_count':479,'categories':[{'name':'Just Chatting'}]}})
        self.assertEqual(stream_details(result),'— Just Chatting · 479')
        result=rumble.resolve(page([video(id=123,watching_now=789,category={'name':'Gaming'})]),CHANNEL)
        self.assertEqual(stream_details(result),'— Gaming · 789')
    def test_details_do_not_change_selection_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cache';p.write_text(json.dumps({'jandro':{'checked_at':time.time(),'viewer_count':479,'category':'Just Chatting','icon':'avatar.png'}}))
            out=io.StringIO()
            with contextlib.redirect_stdout(out):menu(p,'Kick')
            fields=out.getvalue().strip().split('\t')
            self.assertEqual(fields[2],'jandro (Kick)')
            self.assertEqual(fields[3],'avatar.png')
            self.assertEqual(fields[4],'— Just Chatting · 479')
