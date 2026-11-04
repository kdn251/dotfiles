-- Bounded requests avoid the slow initial open-ended read seen on YouTube's
-- media servers. Keep this file-local so local files and live streams retain
-- their normal network behavior.
local utils = require('mp.utils')
mp.add_hook('on_load', 50, function()
    local path = mp.get_property('path', '')
    local host = path:match('^https?://([^/]+)/')
    if host ~= 'youtube.com' and host ~= 'www.youtube.com' and
        host ~= 'm.youtube.com' and host ~= 'youtu.be' then return end
    -- ytdl_hook (priority 10) has finished resolving the selected formats.
    local result = mp.get_property_native('user-data/mpv/ytdl/json-subprocess-result')
    if type(result) ~= 'table' or result.status ~= 0 or type(result.stdout) ~= 'string' then return end
    local data = utils.parse_json(result.stdout)
    if type(data) ~= 'table' or data.is_live or data.live_status == 'is_live' or data.live_status == 'is_upcoming' then return end
    local id = path:match('[?&]v=([%w_-]+)') or path:match('youtu%.be/([%w_-]+)') or
        path:match('/shorts/([%w_-]+)') or path:match('/live/([%w_-]+)')
    if not id or data.id ~= id then return end
    mp.set_property('file-local-options/stream-lavf-o',
        'request_size=1048576,initial_request_size=131072,multiple_requests=1')
end)
