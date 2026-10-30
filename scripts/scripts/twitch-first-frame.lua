-- A reusable Twitch player updates chat identity and first-frame readiness
-- together when switching streams, rather than relying on startup environment.
local path = os.getenv('TWITCH_FIRST_FRAME')
local expected = nil
local reported = false
local fallback = os.getenv('TWITCH_FALLBACK_URL')
mp.set_property_native('user-data/twitch-managed', 2)
mp.set_property_native('user-data/stream-service', os.getenv('STREAM_TITLE_SERVICE') or 'Twitch')
mp.set_property_native('user-data/stream-name', os.getenv('STREAM_TITLE_NAME') or os.getenv('TWITCH_STREAMER_USERNAME') or '')
mp.set_property('user-data/twitch-channel', os.getenv('TWITCH_STREAMER_USERNAME') or '')
mp.register_script_message('twitch-load', function(channel, title, url, marker, low_url, service)
    service = service or 'Twitch'
    mp.set_property_native('user-data/stream-service', service)
    mp.set_property_native('user-data/stream-name', channel)
    fallback = low_url
    path = marker
    expected = url
    reported = false
    mp.set_property('user-data/twitch-channel', channel)
    mp.set_property('force-media-title', title)
    mp.set_property_native('pause', false)
    local options = {['user-agent']='Mozilla/5.0', referrer='', ['ytdl-format']='bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best'}
    if service == 'Kick' or service == 'Rumble' then options.referrer = 'https://' .. service:lower() .. '.com/' end
    mp.command_native({'loadfile', url, 'replace', 0, options})
end)
mp.register_event('playback-restart', function()
    if reported or not path then return end
    if expected and mp.get_property('path') ~= expected then return end
    reported = true
    local file = io.open(path, 'w')
    if file then file:write('playing'); file:close() end
end)

-- Direct HLS avoids opening the manifest twice. Keep a normal URL fallback
-- for FFmpeg changes or streams the explicit HLS reader cannot handle.
local current_path = nil
mp.register_event('start-file', function()
    current_path = mp.get_property('path')
end)
mp.register_event('end-file', function(event)
    if event.reason ~= 'error' or not current_path then return end
    local plain = current_path:match('^av://hls:(https://.+)')
    local target = plain
    if not target and not reported and fallback and fallback ~= '' then
        target = fallback
        fallback = nil
    end
    if not target then return end
    if expected == current_path then expected = target end
    current_path = target
    mp.commandv('loadfile', target, 'replace')
end)
