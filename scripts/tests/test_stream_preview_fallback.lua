-- A failed direct URL must leave time for twitch-first-frame's fallback load.
local events,properties,commands={},{},{}
package.preload['mp.assdraw']=function() return {} end
mp={
 create_osd_overlay=function() return {remove=function() end} end,
 add_periodic_timer=function() return {kill=function() end} end,
 observe_property=function() end,
 register_event=function(name,fn) events[name]=fn end,
 add_forced_key_binding=function() end,
 register_script_message=function() end,
 set_property_native=function(key,value) properties[key]=value end,
 commandv=function(...) table.insert(commands,{...}) end,
 osd_message=function() end,
}
dofile('scripts/scripts/stream-preview.lua')
events['end-file']({reason='error'})
assert(#commands==0,'Preview quit before fallback could recover')
events['playback-restart']()
assert(properties['user-data/preview-ready']==true,'Recovered stream was not marked ready')
print('Preview survives direct URL failure and accepts fallback playback')
