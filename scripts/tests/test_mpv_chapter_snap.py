from pathlib import Path
import subprocess
import tempfile
import unittest

class ChapterSnapTests(unittest.TestCase):
    def test_snap_release_scaling_and_non_seek_sliders(self):
        source=(Path(__file__).resolve().parents[2]/'mpv/.config/mpv/scripts/osc.lua').read_text()
        function=source[source.index('function get_slider_value(element)'):source.index('\nfunction countone',source.index('function get_slider_value(element)'))]
        harness=r'''
local mouse, scale, duration = 508, 1, 100
local chapters={{time=0},{time=50},{time=80}}
mp={get_property_number=function() return duration end,get_property_native=function() return chapters end}
function get_virt_mouse_pos() return mouse end
function get_virt_scale_factor() return scale end
function scale_value(a,b,c,d,v) return c+(v-a)/(b-a)*(d-c) end
function get_slider_value_at(e,x) return scale_value(e.slider.min.glob_pos,e.slider.max.glob_pos,0,100,x) end
'''+function+r'''
local e={name='seekbar',state={},slider={min={value=0,glob_pos=0},max={value=100,glob_pos=1000}}}
assert(get_slider_value(e)==50 and e.state.chapter_snap==50)
mouse=515;assert(get_slider_value(e)==50)
mouse=517;assert(math.abs(get_slider_value(e)-51.7)<.001 and e.state.chapter_snap==nil)
mouse=797;assert(get_slider_value(e)==80)
mouse=4;assert(get_slider_value(e)==0)
scale=2;e.slider.max.glob_pos=2000;mouse=1016;assert(get_slider_value(e)==50)
mouse=1034;assert(math.abs(get_slider_value(e)-51.7)<.001)
e.name='volume';mouse=1008;assert(get_slider_value(e)==50.4)
e.name='seekbar';chapters={};assert(get_slider_value(e)==50.4 and e.state.chapter_snap==nil)
duration=0;assert(get_slider_value(e)==50.4)
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'snap.lua';path.write_text(harness)
            subprocess.run(['lua',str(path)],check=True,capture_output=True)
