-- Loaded only by the managed live-stream player, never Newsboat video players.
local helper = os.getenv('HOME') .. '/scripts/stream-watch-state.py'
local moving = false
local function identity()
    return mp.get_property_native('user-data/stream-service','Twitch'),
           mp.get_property_native('user-data/stream-name','')
end
local function run(args, callback)
    local command={'python3',helper}
    for _,v in ipairs(args) do command[#command+1]=v end
    mp.command_native_async({name='subprocess',playback_only=false,args=command,
        capture_stdout=true,capture_stderr=true},function(ok,result)
        if callback then callback(ok and result and result.status==0 and result.stdout:gsub('%s+$','') or '') end
    end)
end
mp.observe_property('user-data/stream-ready-session','native',function(_,session)
    if not session or session=='' then return end
    moving=false
    local service,name=identity()
    if name~='' then run({'record',service,name}) end
end)
local function navigate(direction)
    if moving then return end
    if mp.get_property_native('user-data/stream-ready-session','')=='' then return end
    moving=true
    run({'step',tostring(direction)},function(message)
        if message~='' then mp.osd_message(message,2) end
        mp.add_timeout(2,function() moving=false end)
    end)
end
mp.add_forced_key_binding('<','stream-history-back',function() navigate(-1) end)
mp.add_forced_key_binding('>','stream-history-forward',function() navigate(1) end)
