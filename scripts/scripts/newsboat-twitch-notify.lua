-- Notify once playback actually starts, including downloaded VODs.
local utils = require('mp.utils')
local sent
local original = os.getenv("NEWSBOAT_MEDIA_URL") or ""
mp.register_event('playback-restart', function()
    local url = mp.get_property_native('user-data/newsboat/url', original)
    if not url:match('twitch%.tv/videos/%d+') or sent == url then return end
    sent = url
    local helper = os.getenv('NEWSBOAT_TWITCH_NOTIFY')
    if not helper then return end
    mp.command_native_async({name='subprocess', playback_only=false, args={
        'python3', helper, url,
        mp.get_property('path', ''), mp.get_property('media-title', ''),
        utils.format_json(mp.get_property_native('metadata', {}))
    }}, function(success, result, error)
        if not success or (result and result.status ~= 0) then
            mp.msg.warn('Twitch notification failed: ' .. tostring(error or (result and result.stderr)))
        end
    end)
end)
