from pathlib import Path
import shutil
import subprocess
import unittest

OSC=Path(__file__).resolve().parents[2]/'mpv/.config/mpv/scripts/osc.lua'

@unittest.skipUnless(shutil.which('lua'),'requires Lua')
class PortraitRequestsTests(unittest.TestCase):
    def test_same_creator_requests_are_coalesced_and_stale_results_ignored(self):
        source=OSC.read_text()
        block=source[source.index('local portrait ='):source.index('local function portrait_title')]
        driver='''
local url='https://youtu.be/aaaaaaaaaaa'
local jobs,callbacks,observers,aborted={},{},{},{}
local function request_tick() end
mp={}
mp.get_property_native=function(key,default)
    if key=='user-data/newsboat/url' then return url end
    return default
end
mp.commandv=function() end
mp.observe_property=function(key,kind,callback) observers[key]=callback;callback() end
mp.register_event=function() end
mp.abort_async_command=function(id) aborted[#aborted+1]=id end
mp.command_native_async=function(spec,callback)
    jobs[#jobs+1]=spec;callbacks[#callbacks+1]=callback;return #jobs
end
'''+block+'''
assert(#jobs==1,'initial observers started duplicate avatar requests')
url='https://youtu.be/bbbbbbbbbbb'
observers['user-data/newsboat/url']()
assert(#jobs==2)
assert(#aborted==1 and aborted[1]==1)
callbacks[1](true,{status=0,stdout='/old-avatar'})
assert(portrait.path==nil,'stale creator response was displayed')
callbacks[2](true,{status=0,stdout='/new-avatar'})
assert(portrait.path=='/new-avatar')
observers['user-data/stream-service']()
assert(#jobs==2,'completed creator was requested again')
'''
        result=subprocess.run(['lua','-'],input=driver,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
