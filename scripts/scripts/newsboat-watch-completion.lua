-- Track completion of explicit local downloads, including very short videos.
local helper = os.getenv('NEWSBOAT_MAINTENANCE')
local url = os.getenv('NEWSBOAT_MEDIA_URL')
if not helper or not url then return end
local restored = false
local reported = false
local path = ''
local position, duration
local function save_progress()
    -- Read the latest seek position even if its observer callback is queued.
    position = mp.get_property_number('time-pos') or position
    duration = mp.get_property_number('duration') or duration
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
-- Save before mpv clears time-pos/duration during close or loadfile replacement.
mp.add_hook('on_unload', 50, save_progress)
mp.register_event('end-file', function(event)
    if event.reason == 'eof' and duration then position = duration end
    save_progress()
end)
mp.register_event('shutdown', save_progress)
mp.register_event('file-loaded', function()
    -- Only the first load resumes from storage. A streaming-to-local handoff
    -- supplies its own current position and must not jump backwards.
    if not restored then
        restored = true
        local total = mp.get_property_number('duration', 0)
        local result = mp.command_native({name='subprocess', playback_only=false,
            capture_stdout=true, args={'python3', helper, 'resume', url, tostring(total)}})
        local resume = result and result.status == 0 and tonumber(result.stdout) or 0
        if resume and resume > 0 then mp.commandv('seek', tostring(resume), 'absolute+exact') end
    end
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
