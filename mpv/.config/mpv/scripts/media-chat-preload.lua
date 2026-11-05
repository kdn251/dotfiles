-- Start optional browser work only after the first decoded frame. Never wait
-- for it in a playback hook; previews remain cheap until explicitly selected.
local utils = require('mp.utils')
local timer
local requested
local function schedule()
    if timer then timer:kill() end
    timer=mp.add_timeout(0.75,function()
        timer=nil
        local app_id=mp.get_property('options/wayland-app-id')
        if app_id=='stream-preview' or app_id=='stream-staging' then return end
        if mp.get_property_number('time-pos')==nil then return end
        local service=mp.get_property_native('user-data/stream-service','')
        local url=mp.get_property_native('user-data/newsboat/url',os.getenv('NEWSBOAT_MEDIA_URL') or '')
        local session=mp.get_property_native('user-data/stream-ready-session','')
        if service=='Twitch' then return end -- launcher owns Chatterino
        if url=='' and service=='' then return end
        local key=service..'|'..url..'|'..session
        if key==requested then return end
        requested=key
        mp.command_native_async({name='subprocess',playback_only=false,
            capture_stdout=true,capture_stderr=true,
            args={'python3',os.getenv('HOME')..'/scripts/media-chat.py',
                  '--preload',tostring(utils.getpid())}},function() end)
    end)
end
mp.register_event('start-file',function()
    if timer then timer:kill();timer=nil end
end)
mp.register_event('playback-restart',schedule)
mp.observe_property('user-data/stream-ready-session','native',schedule)
mp.observe_property('options/wayland-app-id','string',schedule)
