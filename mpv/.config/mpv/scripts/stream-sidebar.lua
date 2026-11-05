local utils = require 'mp.utils'
local active = false
local serial = 0
local keys = {j='down',k='up',DOWN='down',UP='up',ENTER='choose',ESC='close',['/']='search'}
local function send(action)
    serial=serial+1
    mp.set_property_native('user-data/stream-sidebar-action',{action=action,serial=serial})
end
local function navigation(_,layout)
    active=type(layout)=='table' and (layout.left or 0)>0
    for key,action in pairs(keys) do
        local binding='sidebar-capture-'..key
        mp.remove_key_binding(binding)
        if active then
            mp.add_forced_key_binding(key,binding,function() send(action) end,{repeatable=true})
        end
    end
end
mp.observe_property('user-data/media-panel-layout','native',navigation)
local function open_sidebar()
    if active then send('close');return end
    if not mp.get_property_bool('fullscreen',false) then return end
    mp.command_native_async({name='subprocess',playback_only=false,detach=true,
        capture_stdout=false,capture_stderr=false,
        args={'python3',os.getenv('HOME')..'/scripts/stream-sidebar.py',tostring(utils.getpid())}},
        function(ok,result)
            if not ok or not result or result.status~=0 then
                mp.osd_message('Could not open live channels',2)
            end
        end)
end
mp.observe_property('user-data/stream-service','native',function(_,service)
    mp.remove_key_binding('stream-live-sidebar')
    if service and service~='' then
        mp.add_forced_key_binding('TAB','stream-live-sidebar',open_sidebar)
    end
end)
