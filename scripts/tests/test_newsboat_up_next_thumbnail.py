import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('thumbnail',SCRIPTS/'newsboat-up-next-thumbnail.py')
thumbnail=importlib.util.module_from_spec(spec);spec.loader.exec_module(thumbnail)


class UpNextThumbnailTests(unittest.TestCase):
    def test_raw_pixels_and_offline_cache(self):
        image=io.BytesIO();Image.new('RGB',(640,360),'red').save(image,'PNG')
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_CACHE_HOME=folder),patch.object(thumbnail,'fetch_png',return_value=image.getvalue()) as fetch:
            result=thumbnail.prepare('https://youtu.be/abcdefghijk')
            data=Path(result['path']).read_bytes()
            self.assertEqual(len(data),480*270*4)
            self.assertEqual(data[:4],b'\0\0\xff\xff')
            self.assertEqual(thumbnail.prepare('https://www.youtube.com/watch?v=abcdefghijk'),result)
            fetch.assert_called_once()

    def test_countdown_overlay_lifecycle(self):
        harness=r'''
local events, observers, keys = {}, {}, {}
local commands, requests = {}, 0
local image_callback
local timer
local plan={enabled=true,playlist=true,next={url='https://youtu.be/abcdefghijk',title='Next video'}}
package.preload['mp.utils']=function() return {
 split_path=function() return '/tmp/' end,
 parse_json=function(value)
  if value=='plan' then return plan end
  return {path='/tmp/thumbnail.bgra',width=480,height=270}
 end
} end
mp={
 command_native=function(cmd)
  if cmd.name=='subprocess' then return {status=0,stdout='plan'} end
  commands[#commands+1]=cmd
 end,
 command_native_async=function(cmd,callback) requests=requests+1;image_callback=callback;return 99 end,
 abort_async_command=function() end,
 get_property=function(_,default) return default end,
 get_property_native=function() return false end,
 set_property=function() end,set_property_native=function() end,
 get_osd_size=function() return 800,600 end,
 commandv=function(...) commands[#commands+1]={...} end,
 osd_message=function() end,
 add_forced_key_binding=function(key,_,callback) keys[key]=callback end,
 observe_property=function(key,_,callback) observers[key]=callback end,
 register_event=function(key,callback) events[key]=callback end,
 add_periodic_timer=function(_,callback) timer={kill=function() end,tick=callback};return timer end
}
dofile(arg[1])
assert(requests==1,'prefetch once without waiting for EOF')
image_callback(true,{status=0,stdout='image'})
assert(#commands==0,'no picture during ordinary playback')
observers['eof-reached']('eof-reached',true)
local draw=commands[#commands]
assert(draw[1]=='overlay-add' and draw[2]==61)
assert(draw[3]>=0 and draw[4]>=600*.37 and draw[11]<=800*.75 and draw[12]<=600*.50)
assert(math.abs(draw[11]/draw[12]-480/270)<.01, "preserve image proportions")
assert(draw[3]+draw[11]<=800 and draw[4]+draw[12]<=600, "stay inside the window")
observers['osd-dimensions']()
assert(commands[#commands][1]=='overlay-add','redraw after resize')
keys.A()
assert(commands[#commands][1]=='overlay-remove','toggle off removes thumbnail')
local n=#commands
image_callback(true,{status=0,stdout='image'})
assert(#commands==n,'late fetch cannot resurrect a cancelled preview')
keys.A()
observers['eof-reached']('eof-reached',true)
keys['>']()
local removed=false
for i=n+1,#commands do if commands[i][1]=='overlay-remove' then removed=true end end
assert(removed,'manual advance clears the preview')
'''
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'test.lua';script.write_text(harness)
            subprocess.run(['lua',str(script),str(SCRIPTS/'newsboat-playlist-playback.lua')],
                           env=dict(os.environ,NEWSBOAT_MEDIA_URL='https://youtu.be/current0000'),check=True,capture_output=True)
