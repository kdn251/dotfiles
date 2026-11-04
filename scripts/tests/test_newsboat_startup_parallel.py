from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(shutil.which('lua'),'requires Lua')
class StartupParallelTests(unittest.TestCase):
    def run_lua(self,script):
        result=subprocess.run(['lua','-'],input=script,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_resume_lookup_overlaps_load_and_preserves_handoff(self):
        source=(ROOT/'scripts/scripts/newsboat-watch-completion.lua').read_text()
        self.run_lua('''
package.preload['mp.utils']=function() return {} end
local hooks,events,calls,properties={},{},{},{}
local callback
os.getenv=function(key) if key=='NEWSBOAT_MAINTENANCE' then return 'helper' elseif key=='NEWSBOAT_MEDIA_URL' then return 'video-A' end end
mp={}
mp.get_property_native=function(key,default) return default end
mp.get_property_number=function(key,default) if key=='duration' then return 200 end return default end
mp.get_property=function(key,default) return default end
mp.set_property=function(key,value) properties[key]=value end
mp.observe_property=function() end
mp.add_periodic_timer=function() end
mp.add_hook=function(name,priority,fn) hooks[name]=fn end
mp.register_event=function(name,fn) events[name]=fn end
mp.abort_async_command=function() end
mp.command_native=function() error('synchronous resume lookup blocked startup') end
mp.command_native_async=function(spec,fn) calls[#calls+1]=spec;callback=fn;return 1 end
'''+source+'''
hooks.on_load()
assert(#calls==1 and calls[1].args[3]=='resume-spec')
local deferred,continued=false,false
hooks.on_preloaded({defer=function() deferred=true end,cont=function() continued=true end})
assert(deferred and not continued)
callback(true,{status=0,stdout='40%\\n'})
assert(continued)
assert(tonumber(properties['file-local-options/start'])==80)
properties={}
hooks.on_load();hooks.on_preloaded({})
assert(#calls==1,'handoff repeated resume lookup')
assert(properties['file-local-options/start']==nil,'handoff overwrote current playback position')
''')

    def test_optional_metadata_waits_for_playback_and_reuses_resolver(self):
        source=(ROOT/'mpv/.config/mpv/scripts/newsboat-player-info.lua').read_text()
        self.run_lua('''
local events,calls,properties={},{},{}
local scheduled
local data={id='abcdefghijk',chapters={{start_time=12,title='Second chapter'}}}
package.preload['mp.utils']=function() return {parse_json=function() return data end} end
mp={}
mp.get_property_native=function(key,default)
 if key=='user-data/newsboat/url' then return 'https://www.youtube.com/watch?v=abcdefghijk' end
 if key=='user-data/mpv/ytdl/json-subprocess-result' then return {status=0,stdout='json'} end
 return default
end
mp.get_property=function() return 'https://www.youtube.com/watch?v=abcdefghijk' end
mp.get_property_number=function(key,default) return default end
mp.set_property_native=function(key,value) properties[key]=value end
mp.command_native_async=function(spec,fn) calls[#calls+1]=spec;fn(true,{status=0,stdout='Streaming'});return #calls end
mp.add_periodic_timer=function() end
mp.observe_property=function(key,kind,fn) fn() end
mp.register_event=function(key,fn) events[key]=fn end
mp.add_timeout=function(seconds,fn) scheduled=fn;return {kill=function() end} end
'''+source+'''
assert(#calls==0,'metadata work started before playback')
events['start-file']();events['playback-restart']()
assert(#calls==0,'metadata work delayed first frame')
scheduled()
assert(#calls==1 and calls[1].args[3]=='status','chapter extraction was repeated')
assert(properties['chapter-list'][1].time==12)
-- No chapters is also a known result, not a reason to re-extract YouTube.
data.chapters=nil
calls={};events['start-file']();events['playback-restart']();scheduled()
assert(#calls==1 and calls[1].args[3]=='status')
''')

    def test_bounded_requests_only_for_resolved_youtube_videos(self):
        source=(ROOT/'scripts/scripts/newsboat-fast-youtube.lua').read_text()
        self.run_lua("""
local hook,changed
local path='https://www.youtube.com/watch?v=abcdefghijk'
local data={id='abcdefghijk',is_live=false}
package.preload['mp.utils']=function() return {parse_json=function() return data end} end
mp={
 add_hook=function(name,priority,fn) hook=fn end,
 get_property=function() return path end,
 get_property_native=function() return {status=0,stdout='json'} end,
 set_property=function(name,value) changed={name,value} end
}
"""+source+"""
hook()
assert(changed[1]=='file-local-options/stream-lavf-o')
assert(changed[2]:find('initial_request_size=131072',1,true))
for _,status in ipairs({'is_live','is_upcoming'}) do
 changed=nil;data.live_status=status;hook();assert(changed==nil)
end
data.live_status=nil;data.is_live=true;hook();assert(changed==nil)
data.is_live=false;data.id='other';hook();assert(changed==nil)
data.id='abcdefghijk'
for _,url in ipairs({'/tmp/video.mp4','https://twitch.tv/example','https://notyoutube.com/watch?v=abcdefghijk'}) do
 path=url;hook();assert(changed==nil)
end
""")
