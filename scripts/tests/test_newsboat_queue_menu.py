"""Queue menu navigation, async lifetime and safe rendered titles."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
class QueueMenuTests(unittest.TestCase):
 def test_menu_navigation_refresh_and_close(self):
  lua=r'''
local keys, callbacks, selected, text = {}, {}, nil, ''
local images,commands = {},{}
local image_serial=0
local resize, pending_resize, w, h = nil,nil,1280,720
local rows={{url='one',title='First',source='Creator',queue_token='a',percent=12},{url='two',title='Second {test}',source='Other',queue_token='b',percent=35}}
local overlay={update=function(self) text=self.data end,remove=function() text='' end}
local mp={create_osd_overlay=function() return overlay end,get_osd_size=function() return w,h end,
 get_property_number=function(_,default) return default end,add_forced_key_binding=function(k,n,f) keys[k]={name=n,fn=f} end,
 remove_key_binding=function(n) for k,v in pairs(keys) do if v.name==n then keys[k]=nil end end end,
 observe_property=function(_,_,cb) resize=cb end,
 add_timeout=function(_,cb) pending_resize={tick=cb,kill=function(self) self.killed=true end};return pending_resize end,
 commandv=function(...) commands[#commands+1]={...} end,
 command_native=function(c) commands[#commands+1]=c end,
 command_native_async=function(cmd,cb)
 if cmd.args[2]:find('up%-next%-thumbnail') then images[#images+1]=cb;return 100+#images end
 callbacks[#callbacks+1]=cb;return #callbacks end,
 abort_async_command=function() end,add_periodic_timer=function(_,cb) return {kill=function() end} end}
package.preload['mp']=function() return mp end
package.preload['mp.utils']=function() return {parse_json=function(s) if s=='image' then image_serial=image_serial+1;return {path='/tmp/thumbnail'..image_serial..'.bgra',width=384,height=216} end return rows end} end
package.preload['mp.assdraw']=function() return {ass_new=function() return {text='',new_event=function() end,
 append=function(self,s) self.text=self.text..s end,draw_start=function() end,draw_stop=function() end,rect_cw=function() end} end} end
local picker=dofile(arg[1]).new('/tmp/',function() return 'one' end,function(row) selected=row.url end)
picker.toggle();assert(picker.is_open());callbacks[1](true,{status=0,stdout='rows'})
assert(text:find('First') and text:find('Creator') and text:find('12%% watched'))
assert(not text:find('Second {test}',1,true),'escape ASS injection')
assert(#images==2,'fetch visible thumbnails concurrently')
images[1](true,{status=0,stdout='image'})
local found=false
for _,c in ipairs(commands) do if c[1]=='overlay-add' then assert(c[2]==40 and c[11]==96 and c[12]==54);found=true end end
assert(found,'thumbnail rendered beside row')
local before=#commands
keys.j.fn();assert(#commands==before,'selection must retain existing thumbnail overlays')
local previous
for i=1,10 do previous=pending_resize;w=1920;h=1080;resize();if previous then assert(previous.killed) end end
assert(#commands==before,'resize storm coalesced')
pending_resize.tick()
assert(#commands==before+1 and commands[#commands][1]=='overlay-add','resize replaces directly, without removal')
keys.ENTER.fn();assert(selected=='two');assert(not picker.is_open());assert(next(keys)==nil)
images[2](true,{status=0,stdout='image'});assert(text=='','late thumbnail cannot resurrect menu')
picker.toggle();picker.close();callbacks[2](true,{status=0,stdout='rows'});assert(text=='','late callback stays closed')
picker.toggle();callbacks[3](true,{status=0,stdout='rows'});keys.ESC.fn();assert(not picker.is_open())
rows={};picker.toggle();callbacks[4](true,{status=0,stdout='rows'});assert(text:find('Your queue is empty'))
keys.ENTER.fn();assert(picker.is_open());keys.W.fn();assert(not picker.is_open())
rows={}
for i=1,10 do rows[i]={url='video'..i,title='Video '..i,queue_token='token'..i} end
local first_image=#images+1
picker.toggle();callbacks[5](true,{status=0,stdout='rows'})
for i=first_image,first_image+6 do images[i](true,{status=0,stdout='image'}) end
before=#commands
for i=1,4 do keys.j.fn() end
assert(#commands==before+7,'viewport scroll replaces seven thumbnails in place')
for i=before+1,#commands-1 do assert(commands[i][1]=='overlay-add','replace loaded thumbnails without blank frames') end
assert(commands[#commands][1]=='overlay-remove' and commands[#commands][2]==46,'only clear the newly exposed, uncached row')
picker.close()

'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.lua';p.write_text(lua)
   subprocess.run(['lua',str(p),str(SCRIPTS/'newsboat-queue-menu.lua')],check=True,capture_output=True)
 def test_queue_rows_preserve_order_and_progress(self):
  import newsboat_queue as queue
  from unittest.mock import patch
  rows=[dict(url='https://youtu.be/abc123DEF45',title='First',queue_token='a'),dict(url='https://youtu.be/abc123DEF46',title='Second',queue_token='b')]
  with patch.object(queue,'entries',return_value=rows),patch('newsboat_resume.progress',return_value={'youtube:abc123DEF45':(.42,1)}):
   result=queue.menu_rows()
   self.assertEqual([r['queue_token'] for r in result],['a','b'])
   self.assertEqual([r['percent'] for r in result],[42,0])
