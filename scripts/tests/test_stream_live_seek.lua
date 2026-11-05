local properties={['user-data/stream-service']='Twitch',['time-pos']=1249,duration=277,['demuxer-cache-state']={['seekable-ranges']={{start=970,['end']=1250}}}}
local callback,commands,keys=nil,{},{}
mp={get_property_native=function(k,default) return properties[k] or default end,
get_property_number=function(k) return properties[k] end,
register_script_message=function(_,f) callback=f end,
observe_property=function(_,_,f) f() end,
remove_key_binding=function() end,
add_forced_key_binding=function(key,_,f) keys[key]=f end,
commandv=function(...) table.insert(commands,{...}) end,
set_property_native=function(k,v) properties[k]=v end}
dofile('scripts/scripts/stream-live-seek.lua')
keys.k();assert(commands[1][2]==1249.95)
callback(100,'absolute-percent');assert(commands[2][2]==1249.95)
properties['time-pos']=1249.95;keys.l();assert(#commands==2);assert(properties.pause==false)
properties['time-pos']=1000;keys.j();assert(commands[3][2]==970)
properties['user-data/stream-service']='';callback(60,'relative');assert(#commands==3)
print('Live seeks clamp to real timestamps; catching live waits without jumping back.')
