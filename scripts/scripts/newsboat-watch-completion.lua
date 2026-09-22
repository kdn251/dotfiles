-- Track completion of explicit local downloads, including very short videos.
local helper = os.getenv('NEWSBOAT_MAINTENANCE')
local url = os.getenv('NEWSBOAT_MEDIA_URL')
if not helper or not url then return end
local reported = false
local path = ''
mp.register_event('file-loaded', function()
    reported = false
    path = mp.get_property('path', '')
end)
mp.observe_property('percent-pos', 'number', function(_, percent)
    if reported or not percent or percent < 90 or path:sub(1,1) ~= '/' then return end
    reported = true
    -- A short local SQLite write must finish before mpv can exit at EOF.
    mp.command_native({name='subprocess', playback_only=false,
        args={'python3', helper, 'watched', path, url, tostring(percent / 100)}})
end)
