from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[2]/'mpv/.config/mpv/scripts/clip-menu.lua'

class ClipMenuTests(unittest.TestCase):
    def test_lengths_buffer_labels_and_selected_duration(self):
        harness=r'''
local open, command
local bindings = {}
local overlay = {remove=function() end, update=function() end}
package.preload['mp.assdraw']=function() return {ass_new=function()
 return {text='',new_event=function() end,pos=function() end,draw_start=function() end,
 draw_stop=function() end,round_rect_cw=function() end,
 append=function(self,text) self.text=self.text..text end}
end} end
package.preload['mp.utils']=function() return {getpid=function() return 123 end} end
mp={
 get_property_number=function() return 150 end,
 get_property_native=function(name) assert(name=='demuxer-cache-state'); return {['seekable-ranges']={{start=120,['end']=160},{start=100,['end']=125}}} end,
 get_property=function() return '/tmp/test-player.sock' end,
 get_osd_size=function() return 1920,1080 end,
 create_osd_overlay=function() return overlay end,
 osd_message=function() end,
 command_native_async=function(value, callback) command=value;callback(true,{status=0}) end,
 add_key_binding=function(key,name,callback) open=callback end,
 add_forced_key_binding=function(key,name,callback) bindings[key]=callback end,
 remove_key_binding=function(name) bindings[name:sub(11)]=nil end,
 observe_property=function() end,register_event=function() end,
 register_script_message=function() end,
}
dofile(arg[1])
open()
assert(overlay.data:find('50s buffered',1,true))
assert(overlay.data:find('>  Last 30 seconds',1,true))
bindings.j()
assert(overlay.data:find('>  Last 45 seconds',1,true))
bindings.k()
assert(overlay.data:find('>  Last 30 seconds',1,true))
for i=1,4 do bindings.j() end
bindings.ENTER()
assert(command.args[4]=='120')
assert(bindings.j==nil)
open()
bindings.k()
bindings.ENTER()
assert(command.args[4]=='15')
open()
bindings.ESC()
assert(bindings.k==nil)
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'menu.lua';path.write_text(harness)
            subprocess.run(['lua',str(path),str(SCRIPT)],check=True,capture_output=True,text=True)
