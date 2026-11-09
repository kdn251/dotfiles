local utils=require 'mp.utils'
mp.set_property_native('user-data/multiview-bindings',4)
local function action(value,direction)
    local code="import sys;sys.path.insert(0,sys.argv[1]);from stream_multiview import send;send(int(sys.argv[2]),sys.argv[3],direction=sys.argv[4],key=sys.argv[4])"
    mp.command_native_async({name='subprocess',playback_only=false,args={'python3','-c',code,
        os.getenv('HOME')..'/scripts',tostring(utils.getpid()),value,direction or ''}},function() end)
end
local function bindings()
    local active=mp.get_property_native('user-data/stream-multiview',false)==true
        and mp.get_property_bool('fullscreen',false)
    -- The native window may still own keyboard focus while another pane
    -- plays audio. Route ordinary playback commands to that selected player.
    local selected=mp.get_property_number('user-data/stream-multiview-selected',0)
    for _,key in ipairs({'S','C','+','-','_','Ctrl+c','SPACE','m','h','l','LEFT','RIGHT','[',']','{','}','H','J','K','L'}) do
        local binding='multiview-playback-'..key
        mp.remove_key_binding(binding)
        if active and selected>0 then
            mp.add_forced_key_binding(key,binding,function() action('key',key) end,{repeatable=true})
        end
    end
    for _,key in ipairs({'h','j','k','l'}) do
        mp.remove_key_binding('multiview-swap-'..key)
        if active then mp.add_forced_key_binding('Ctrl+Shift+'..key,'multiview-swap-'..key,function() action('swap',key) end) end
        mp.remove_key_binding('multiview-'..key)
        if active then mp.add_forced_key_binding('Ctrl+'..key,'multiview-'..key,function() action('move',key) end) end
    end
    for key,value in pairs({q='close',ENTER='zoom',ESC='grid'}) do
        mp.remove_key_binding('multiview-'..value)
        if active then mp.add_forced_key_binding(key,'multiview-'..value,function() action(value) end) end
    end
end
mp.observe_property('user-data/stream-multiview','bool',bindings)
mp.observe_property('fullscreen','bool',bindings)

mp.observe_property('user-data/stream-multiview-selected','number',bindings)
