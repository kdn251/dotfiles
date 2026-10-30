import importlib.util
import io
import json
from pathlib import Path
import unittest
import subprocess
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('refresh', Path(__file__).resolve().parents[1] / 'scripts/stream-title-refresh.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class RefreshTests(unittest.TestCase):
    def test_live_metadata_and_offline_response(self):
        data = {'data': {'user': {'stream': {'title': 'New\n title', 'viewersCount': 1200,
                                          'game': {'displayName': 'New game'}}}}}
        with patch.object(helper, 'urlopen', return_value=io.BytesIO(json.dumps(data).encode())):
            self.assertEqual(helper.refresh('Example', 'Twitch'),
                             'Example — New game ·  1.2k | New title')
        with patch.object(helper, 'urlopen', return_value=io.BytesIO(b'{"data":{"user":null}}')):
            self.assertEqual(helper.refresh('Example', 'Twitch'), '')

    def test_other_platform_cache_and_expiration(self):
        data = {'k': {'example': {'title': 'Updated title', 'checked_at': 1000}}}
        with patch.object(helper, 'load', return_value=data), patch.object(helper.time, 'time', return_value=1001):
            self.assertEqual(helper.refresh('Example', 'Kick'), 'Example | Updated title')
        with patch.object(helper, 'load', return_value=data), patch.object(helper.time, 'time', return_value=2000):
            self.assertEqual(helper.refresh('Example', 'Kick'), '')

    def test_player_ignores_late_response_from_previous_channel(self):
        harness = r"""
local props = {['user-data/twitch-channel']='first', ['force-media-title']='Original'}
local timers, callbacks, observe, events = {}, {}, nil, {}
mp = {
 get_property=function(k, default) return props[k] or default end,
 get_property_native=function(k, default) return props[k] or default end,
 set_property=function(k, v) props[k]=v end,
 observe_property=function(k,t,cb) observe=cb end,
 add_timeout=function(t,cb) timers.first=cb end,
 get_time=function() return clock or 100 end,
 add_periodic_timer=function(t,cb) if t==1 then timers.tick=cb else timers.periodic=cb end end,
 register_event=function(k,cb) events[k]=cb end,
 command_native_async=function(cmd,cb) callbacks[#callbacks+1]=cb; return #callbacks end,
 abort_async_command=function() end,
}
dofile(arg[1])
timers.first()
props['user-data/twitch-channel']='second'; observe()
callbacks[1](true,{status=0,stdout='Wrong streamer'})
assert(props['force-media-title']=='Original')
-- A stale result schedules the new channel immediately, not after a minute.
timers.first()
assert(#callbacks == 2)
timers.periodic()
callbacks[2](true,{status=0,stdout='Second — New game | New title\n'})
assert(props['force-media-title']=='Second — New game | New title')
timers.periodic()
callbacks[3](false,{status=1,stdout=''})
assert(props['force-media-title']=='Second — New game | New title')
callbacks[3](true,{status=0,stdout='Second — 1:59:59 | Title'})
clock=101
timers.tick()
assert(props['force-media-title']=='Second — 2:00:00 | Title')
props['user-data/twitch-channel']='third'; observe()
timers.tick()
assert(props['force-media-title']=='Second — 2:00:00 | Title')
events.shutdown()
"""
        with tempfile.TemporaryDirectory() as tmp:
            test = Path(tmp) / 'test.lua'
            test.write_text(harness)
            subprocess.run(['lua', str(test), str(Path(helper.__file__).with_suffix('.lua'))],
                           check=True, capture_output=True, text=True)
