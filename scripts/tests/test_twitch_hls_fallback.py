from pathlib import Path
import subprocess
import tempfile
import unittest


class HLSFallbackTests(unittest.TestCase):
    def test_fallback_once_preserves_first_frame_and_ignores_normal_quit(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/twitch-first-frame.lua'
        with tempfile.TemporaryDirectory() as tmp:
            marker = str(Path(tmp) / 'ready')
            harness = r'''
local events, messages, commands, properties = {}, {}, {}, {}
mp = {
    register_event = function(name, callback) events[name] = callback end,
    register_script_message = function(name, callback) messages[name] = callback end,
    set_property = function(key, value) properties[key] = value end,
    set_property_native = function(key, value) properties[key] = value end,
    get_property = function(key) return properties[key] end,
    commandv = function(...) commands[#commands+1] = {...} end,
}
dofile(arg[1])
local direct = 'av://hls:https://example.test/live.m3u8'
messages['twitch-load']('test', 'Test stream', direct, arg[2])
properties.path = direct
events['start-file']()
events['end-file']({reason='quit'})
assert(#commands == 1)
events['end-file']({reason='error'})
assert(#commands == 2 and commands[2][2] == 'https://example.test/live.m3u8')
properties.path = commands[2][2]
events['start-file']()
events['playback-restart']()
local file = assert(io.open(arg[2], 'r'))
assert(file:read('*a') == 'playing'); file:close()
events['end-file']({reason='error'})
assert(#commands == 2, 'must not retry forever')
-- A new selection replaces the old fallback and can step down only once.
local low = 'av://hls:https://example.test/low.m3u8'
messages['twitch-load']('second', 'Second stream', direct, arg[2], low)
properties.path = direct; events['start-file']()
events['end-file']({reason='error'})
assert(commands[#commands][2] == 'https://example.test/live.m3u8')
properties.path = commands[#commands][2]; events['start-file']()
events['end-file']({reason='error'})
assert(commands[#commands][2] == low)
properties.path = low; events['start-file']()
events['end-file']({reason='error'})
assert(commands[#commands][2] == 'https://example.test/low.m3u8')
properties.path = commands[#commands][2]; events['start-file']()
local count = #commands
events['end-file']({reason='error'})
assert(#commands == count, 'quality fallback must be bounded')
'''
            test = Path(tmp) / 'test.lua'
            test.write_text(harness)
            subprocess.run(['lua', str(test), str(script), marker], check=True,
                           capture_output=True, text=True)
