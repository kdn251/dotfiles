package.preload['mp.utils']=function()return {parse_json=function(v)return v end}end
local props={['user-data/stream-service']='Twitch',['user-data/stream-name']='example',
 ['time-pos']=1010,['demuxer-cache-state']={['seekable-ranges']={{start=1000,['end']=1020}}}}
local callbacks,timers,events,commands={},{},{},{}
local pending
mp={get_property_native=function(k,d)return props[k] or d end,get_property_number=function(k,d)return props[k] or d end,
set_property_native=function(k,v)props[k]=v end,
observe_property=function(k,_,f)callbacks[k]=f;f()end,
add_timeout=function(_,f)timers[#timers+1]=f end,add_periodic_timer=function()end,
register_event=function(k,f)events[k]=f end,abort_async_command=function()end,
command_native_async=function(_,cb)pending=cb;return 1 end,
command_native=function(cmd)commands[#commands+1]=cmd end,commandv=function(...)commands[#commands+1]={...}end,
osd_message=function()end}
local dvr=dofile('scripts/scripts/stream-twitch-dvr.lua')
assert(not dvr.seek(-60,'relative'),'No recording must preserve local seeking')
timers[#timers]()
pending(true,{status=0,stdout={path='/test/vod.m3u8',duration=7200,started_at=os.time()-7200}})
assert(props['user-data/stream-dvr'].available)
assert(not dvr.seek(-5,'relative'),'Short rewinds should use the already buffered stream')
assert(dvr.seek(600,'absolute+exact'))
assert(commands[1][1]=='loadfile' and commands[1][5].start=='600')
assert(props['user-data/stream-dvr'].mode=='rewind')
events['playback-restart']()
assert(dvr.seek(1200,'absolute+exact'))
assert(commands[2][1]=='seek' and commands[2][2]==1200)
assert(dvr.seek(100,'absolute-percent'))
pending(true,{status=0,stdout={best='https://example.org/live.m3u8'}})
assert(commands[3][2]=='https://example.org/live.m3u8')
events['playback-restart']()
assert(props['user-data/stream-dvr'].mode=='live' and not props['user-data/stream-dvr'].loading)
-- In-flight discovery must not restore a previous channel's recording.
timers[#timers]()
local stale=pending
props['user-data/stream-name']='different';callbacks['user-data/stream-name']()
stale(true,{status=0,stdout={path='/old',duration=7200,started_at=1}})
assert(not props['user-data/stream-dvr'].available)
print('DVR fallback, local seek, rewind, return-to-live, and stale requests passed.')
