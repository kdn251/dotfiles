-- A reusable Twitch player updates chat identity and first-frame readiness
-- together when switching streams, rather than relying on startup environment.
local path = os.getenv('TWITCH_FIRST_FRAME')
local expected = nil
local reported = false
mp.set_property_native('user-data/twitch-managed', 1)
mp.set_property('user-data/twitch-channel', os.getenv('TWITCH_STREAMER_USERNAME') or '')
mp.register_script_message('twitch-load', function(channel, title, url, marker)
    path = marker
    expected = url
    reported = false
    mp.set_property('user-data/twitch-channel', channel)
    mp.set_property('force-media-title', title)
    mp.set_property_native('pause', false)
    mp.commandv('loadfile', url, 'replace')
end)
mp.register_event('playback-restart', function()
    if reported or not path then return end
    if expected and mp.get_property('path') ~= expected then return end
    reported = true
    local file = io.open(path, 'w')
    if file then file:write('playing'); file:close() end
end)
