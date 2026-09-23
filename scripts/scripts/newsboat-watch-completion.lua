-- Track completion of explicit local downloads, including very short videos.
local helper = os.getenv('NEWSBOAT_MAINTENANCE')
local url = os.getenv('NEWSBOAT_MEDIA_URL')
if not helper or not url then return end
local reported = false
local path = ''
local position, duration
local function save_progress()
    if not position or not duration or duration <= 0 then return end
    mp.command_native({name='subprocess', playback_only=false,
        args={'python3', helper, 'progress', url, tostring(position), tostring(duration)}})
end
mp.observe_property('time-pos', 'number', function(_, value)
    if value then position = value end
end)
mp.observe_property('duration', 'number', function(_, value)
    if value and value > 0 then duration = value end
end)
mp.add_periodic_timer(5, save_progress)
mp.register_event('end-file', function(event)
    if event.reason == 'eof' and duration then position = duration end
    save_progress()
end)
mp.register_event('shutdown', save_progress)
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
