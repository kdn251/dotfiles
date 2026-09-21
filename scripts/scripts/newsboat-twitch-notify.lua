-- Notify once playback actually starts, including downloaded VODs.
local utils = require('mp.utils')
local sent = false
mp.register_event('playback-restart', function()
    if sent then return end
    sent = true
    local helper = os.getenv('NEWSBOAT_TWITCH_NOTIFY')
    if not helper then return end
    mp.command_native_async({name='subprocess', playback_only=false, args={
        'python3', helper, os.getenv('NEWSBOAT_TWITCH_URL') or '',
        mp.get_property('path', ''), mp.get_property('media-title', ''),
        utils.format_json(mp.get_property_native('metadata', {}))
    }}, function(success, result, error)
        if not success or (result and result.status ~= 0) then
            mp.msg.warn('Twitch notification failed: ' .. tostring(error or (result and result.stderr)))
        end
    end)
end)
