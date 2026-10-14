"""Queue menu navigation, async lifetime and safe rendered titles."""
import os
from pathlib import Path
import subprocess
import json
import shutil
import socket
import time
import tempfile
import unittest
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
class QueueMenuTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which('mpv'), 'requires mpv')
 def test_real_mpv_two_y_keypresses_then_paste(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   rows=[dict(url=str(i),title=f'Video {i}',queue_token=str(i)) for i in range(3)]
   (root/'rows.json').write_text(json.dumps(rows))
   (root/'newsboat-up-next-thumbnail.py').write_text('raise SystemExit(1)\n')
   (root/'newsboat_queue.py').write_text('''import json,sys
from pathlib import Path
p=Path(__file__).with_name('rows.json')
rows=json.loads(p.read_text())
if sys.argv[1]=='menu-json':
 print(json.dumps(rows))
elif sys.argv[1]=='remove':
 rows=[r for r in rows if r['url']!=sys.argv[2]]
 p.write_text(json.dumps(rows))
else:
 source=next(r for r in rows if r['url']==sys.argv[2])
 rows.remove(source)
 at=next(i for i,r in enumerate(rows) if r['url']==sys.argv[3])
 rows.insert(at+(sys.argv[1]=='move-after'),source)
 p.write_text(json.dumps(rows))
''')
   driver=root/'driver.lua'
   driver.write_text("local menu=dofile("+json.dumps(str(SCRIPTS/'newsboat-queue-menu.lua'))+").new("+json.dumps(directory+'/')+",function() return '' end,function() end)\nmp.add_key_binding('W','queue',menu.toggle)\n")
   ipc=root/'ipc'
   proc=subprocess.Popen(['mpv','--no-config','--idle=yes','--vo=null','--ao=null','--input-ipc-server='+str(ipc),'--script='+str(driver)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    deadline=time.monotonic()+5
    while not ipc.exists() and time.monotonic()<deadline:time.sleep(.02)
    with socket.socket(socket.AF_UNIX) as connection:
     connection.settimeout(3);connection.connect(str(ipc));stream=connection.makefile('rb')
     def command(value):
      connection.sendall((json.dumps({'command':value})+'\n').encode())
      while True:
       response=json.loads(stream.readline())
       if 'error' in response:
        self.assertEqual(response['error'],'success');return response.get('data')
     def key(value):
      command(['keypress',value]);time.sleep(.08)
     key('W');time.sleep(.25)
     for keyname in ['y','y','j','j','p']:key(keyname)
     def wait_order(expected):
      deadline=time.monotonic()+3
      while time.monotonic()<deadline:
       if [r['url'] for r in json.loads((root/'rows.json').read_text())]==expected:return
       time.sleep(.03)
      self.fail('Actual MPV keypresses did not reorder the queue')
     wait_order(['1','2','0']);time.sleep(.2)
     key('k');key('P');wait_order(['1','0','2']);time.sleep(.2)
     key('x');wait_order(['1','2']);time.sleep(.2)
     key('x');wait_order(['1']);time.sleep(.2)
     key('x');wait_order([]);time.sleep(.2)
     key('x');wait_order([])
     key('ESC')
     bindings=command(['get_property','input-bindings'])
     self.assertFalse(any(b.get('owner')=='driver' and b.get('key') in ('y','p','P','x') for b in bindings))
   finally:
    proc.terminate();proc.wait(timeout=5)
 def test_menu_navigation_refresh_and_close(self):
  lua=r'''
local keys, callbacks, selected, text = {}, {}, nil, ''
local images,commands = {},{}
local moves = {}
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
 if cmd.args[3]=='move-before' or cmd.args[3]=='move-after' then moves[#moves+1]={args=cmd.args,done=cb};return 200+#moves end
 if cmd.args[2]:find('up%-next%-thumbnail') then images[#images+1]=cb;return 100+#images end
 callbacks[#callbacks+1]=cb;return #callbacks end,
 abort_async_command=function() end,add_periodic_timer=function(_,cb) return {kill=function() end} end}
package.preload['mp']=function() return mp end
package.preload['mp.utils']=function() return {parse_json=function(s) if s=='image' then image_serial=image_serial+1;return {path='/tmp/thumbnail'..image_serial..'.bgra',width=384,height=216} end return rows end} end
package.preload['mp.assdraw']=function() return {ass_new=function() return {text='',new_event=function() end,
 append=function(self,s) self.text=self.text..s end,draw_start=function() end,draw_stop=function() end,rect_cw=function() end} end} end
local picker=dofile(arg[1]).new('/tmp/',function() return 'one' end,function(row) selected=row.url end)
picker.toggle();assert(picker.is_open());callbacks[1](true,{status=0,stdout='rows'})
assert(text:find('NOW PLAYING'),'playing row has an explicit label')
assert(text:find('First') and text:find('Creator') and text:find('12%% watched'))
assert(not text:find('Second {test}',1,true),'escape ASS injection')
assert(#images==2,'fetch visible thumbnails concurrently')
images[1](true,{status=0,stdout='image'})
local found=false
for _,c in ipairs(commands) do if c[1]=='overlay-add' then assert(c[2]==50 and c[11]==96 and c[12]==54);found=true end end
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
for i=1,6 do keys.j.fn() end
assert(#commands==before,'moving within the viewport leaves every thumbnail untouched')
keys.j.fn()
assert(#commands==before+7,'viewport scroll replaces seven thumbnails in place')
for i=before+1,#commands-1 do assert(commands[i][1]=='overlay-add','replace loaded thumbnails without blank frames') end
assert(commands[#commands][1]=='overlay-remove' and commands[#commands][2]==56,'only clear the newly exposed, uncached row')
for _,command in ipairs(commands) do
 if command[1]=='overlay-add' or command[1]=='overlay-remove' then
  assert(command[2]>=50 and command[2]<=56,'Queue must not collide with thumbfast overlay 42')
 end
end
assert(text:find(' b ',1,true),'panel uses rounded Bezier corners')
assert(#images>=first_image+8,'nearby offscreen thumbnails are prefetched')
picker.close()
local a,b,c=rows[1],rows[2],rows[3]
rows={a,b,c};picker.toggle();callbacks[6](true,{status=0,stdout='rows'})
keys.p.fn();assert(#moves==0 and text:find('Press yy'))
keys.y.fn();assert(text:find('Press y again'))
keys.y.fn();assert(text:find('Picked up:'))
keys.j.fn();keys.j.fn();keys.p.fn()
assert(#moves==1 and moves[1].args[3]=='move-after' and moves[1].args[4]==a.url and moves[1].args[5]==c.url)
keys.k.fn();keys.j.fn();assert(text:find('Moving queue row'),'navigation remains available during reorder')
keys.p.fn();assert(#moves==1,'prevent overlapping mutations')
rows={b,c,a};moves[1].done(true,{status=0});callbacks[7](true,{status=0,stdout='rows'})
keys.k.fn();keys.P.fn()
assert(moves[2].args[3]=='move-before' and moves[2].args[4]==a.url and moves[2].args[5]==c.url)
rows={b,a,c};moves[2].done(true,{status=0});callbacks[8](true,{status=0,stdout='rows'})
keys.ENTER.fn();assert(selected==a.url,'selection follows moved row')
assert(not keys.p and not keys.P and not keys.y,'normal playback bindings restored on close')

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
