local events,observers,props={},{},{}
local now=0
local updates,removes=0,0
local overlay={remove=function() removes=removes+1 end,update=function() updates=updates+1 end}
package.preload['mp.assdraw']=function()
    return {ass_new=function() return setmetatable({text=''}, {__index=function() return function() end end}) end}
end
mp={create_osd_overlay=function() return overlay end,
    get_property_native=function(k,d) if props[k]~=nil then return props[k] end return d end,
    get_time=function() return now end,get_osd_size=function() return 640,360 end,
    observe_property=function(k,_,f) observers[k]=f end,
    register_event=function(k,f) events[k]=f end,
    add_periodic_timer=function(_,f) mp.tick=f end}
dofile('scripts/scripts/stream-buffering.lua')
events['playback-restart']()
props['paused-for-cache']=true
mp.tick();assert(updates==0)
now=.6;mp.tick();assert(updates==1)
props.pause=true;mp.tick();assert(updates==1)
props.pause=false;props['user-data/stream-multiview']=true
now=1;mp.tick();now=2;mp.tick();assert(updates==1)
props['user-data/stream-multiview']=false;mp.tick();assert(updates==2)
events['end-file']();mp.tick();assert(updates==2)
assert(removes>0)
print('PASS: buffering delay, user pause, multi-view ownership, and end cleanup')
