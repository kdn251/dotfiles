import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('watch',SCRIPTS/'stream-watch-state.py')
watch=importlib.util.module_from_spec(spec);spec.loader.exec_module(watch)

class WatchTests(unittest.TestCase):
    def test_back_forward_and_new_branch(self):
        state={}
        a,b,c,d=[dict(service='Twitch',name=n) for n in 'abcd']
        for item in (a,b,c):watch.record(state,item)
        self.assertEqual(watch.step(state,-1),b)
        self.assertEqual(state['index'],2)  # Failed navigation leaves current position intact.
        watch.record(state,b)
        self.assertEqual(state['items'],[a,b,c])
        self.assertEqual(watch.step(state,1),c)
        watch.record(state,c)
        watch.step(state,-1);watch.record(state,b);watch.record(state,d)
        self.assertEqual(state['items'],[a,b,d])
        self.assertIsNone(watch.step(state,1))

    def test_repeated_ready_does_not_duplicate(self):
        state={};item=dict(service='Kick',name='example')
        watch.record(state,item);watch.record(state,item)
        self.assertEqual(state['items'],[item])
        self.assertIsNone(watch.step(state,-1))

    def test_live_stream_navigation_bindings(self):
        harness=r'''
local props={['user-data/stream-ready-session']='s1',['user-data/stream-name']='one',['keep-open']='no'}
local keys, observers, timers, requests, commands={},{},{},{},{}
mp={
 get_property_native=function(k,d) if props[k]==nil then return d end return props[k] end,
 get_property=function(k,d) return props[k] or d end,
 set_property=function(k,v) props[k]=v end,
 set_property_native=function(k,v) props[k]=v end,
 add_key_binding=function(k,n,cb) keys[k]=cb end,
 add_forced_key_binding=function(k,n,cb) keys[k]=cb end,
 observe_property=function(k,t,cb) observers[k]=cb end,
 add_periodic_timer=function(t,cb) timers[t]=cb end,
 add_timeout=function(t,cb) cb() end,
 osd_message=function() end,
 commandv=function(...) commands[#commands+1]={...} end,
 command_native_async=function(req,cb) requests[#requests+1]={req=req,cb=cb} end,
}
local function reply(s) requests[#requests].cb(true,{status=0,stdout=s}) end
local function ready(s) props['user-data/stream-ready-session']=s;observers['user-data/stream-ready-session']('',s) end
dofile(arg[1])
ready('s1');assert(requests[#requests].req.args[3]=='record')
keys['<']();assert(requests[#requests].req.args[3]=='step');reply('Switching')
keys['>']();assert(requests[#requests].req.args[4]=='1');reply('Switching')
assert(keys.Z==nil)
assert(timers[30]==nil)
assert(#commands==0)
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'check.lua';path.write_text(harness)
            subprocess.run(['lua',str(path),str(SCRIPTS/'stream-watch-controls.lua')],check=True,capture_output=True)
