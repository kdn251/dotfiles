"""Long titles must replace, rather than append to, the fixed ASS position."""
from pathlib import Path
import subprocess
import tempfile
import unittest

OSC = Path(__file__).resolve().parents[2] / 'mpv/.config/mpv/scripts/osc.lua'


class TitleScrollTests(unittest.TestCase):
    def test_scroll_moves_single_position_with_fixed_clip(self):
        source = OSC.read_text()
        scroll = source[source.index('local title_measure ='):source.index('mp.add_periodic_timer(0.05')]
        render = source[source.index('            local maxchars = element.layout.button.maxchars'):source.index('            if not (maxchars == nil) and (#buttontext > maxchars)')]
        harness = r'''
local now = 0
mp = {get_time=function() return now end, create_osd_overlay=function()
    return {update=function() return {x0=0,x1=900} end}
end}
osc_param = {playresx=1280, playresy=720}
'''+scroll+r'''
local element = {name='title',layout={geometry={x=100,y=600,w=300,h=20,an=4},
    style='{\\fs18}',button={maxchars=20}}}
local function frame()
    local buttontext = 'A long stream title that must remain complete'
    local elem_ass = {text='{\\pos(100,600)\\an4\\clip(100,580,400,620)}'}
'''+render+r'''
    assert(maxchars == nil)
    local result = elem_ass.text .. buttontext
    local _, positions = result:gsub('\\pos%b()', '')
    local _, clips = result:gsub('\\clip%b()', '')
    assert(positions == 1 and clips == 1, result)
    assert(result:find('A long stream title that must remain complete', 1, true))
    return tonumber(result:match('\\pos%(([%d%.%-]+),'))
end
local initial = frame()
now = 2
assert(frame() < initial, 'Title position did not advance')
now = 20
assert(frame() <= initial)
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scroll.lua'
            path.write_text(harness)
            subprocess.run(['lua', str(path)], check=True, capture_output=True)
