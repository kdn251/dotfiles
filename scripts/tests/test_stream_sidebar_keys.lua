package.preload['mp.utils']=function()return {}end
local properties={['user-data/stream-sidebar-open']=true,fullscreen=true,
    ['user-data/media-panel-layout']={left=.04}}
local keys,messages,observers={},{},{}
mp={
 get_property_native=function(k,default)if properties[k]==nil then return default end return properties[k] end,
 get_property_bool=function(k,default)if properties[k]==nil then return default end return properties[k] end,
 set_property_native=function(k,v)properties[k]=v end,
 observe_property=function(k,_,fn) observers[k]=fn;fn(k,properties[k]) end,
 remove_key_binding=function(name)keys[name]=nil end,
 add_forced_key_binding=function(key,name,fn)keys[name]=fn end,
 register_script_message=function(name,fn)messages[name]=fn end,
 command_native_async=function()error('Navigation must not spawn a process')end,
 osd_message=function()end,
}
dofile('mpv/.config/mpv/scripts/stream-sidebar.lua')
local function expect(action)assert(properties['user-data/stream-sidebar-action'].action==action)end
for _,event in ipairs({'down','repeat','press'}) do
 keys['sidebar-capture-j']({event=event});expect('down-start')
 keys['sidebar-capture-k']({event=event});expect('up-start')
end
keys['sidebar-capture-j']({event='up'});expect('nav-stop')
-- Geometry may be zero during a panel animation; the visible sidebar still owns navigation.
properties['user-data/media-panel-layout']={left=0}
observers['user-data/media-panel-layout'](nil,properties['user-data/media-panel-layout'])
assert(keys['sidebar-capture-j'])
messages['stream-sidebar-navigate']('down');expect('down-start')
messages['stream-sidebar-navigate']('up');expect('up-start')
local serial=properties['user-data/stream-sidebar-action'].serial
properties['user-data/stream-sidebar-open']=false
observers['user-data/stream-sidebar-open']()
messages['stream-sidebar-navigate']('down')
assert(properties['user-data/stream-sidebar-action'].serial==serial)
assert(not keys['sidebar-capture-j'])
print('Sidebar navigation accepts physical and synthetic keys and direct multi-view routing.')
