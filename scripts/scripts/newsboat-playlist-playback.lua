-- Autoplay uses the same launcher as manual playback: local copies, resume,
-- history and per-video source context continue to work for each new player.
local utils = require('mp.utils')
local directory = utils.split_path(debug.getinfo(1, 'S').source:sub(2))
local current = os.getenv('NEWSBOAT_MEDIA_URL')
if not current then return end
local result = mp.command_native({name='subprocess', playback_only=false, capture_stdout=true,
    args={'python3', directory .. 'newsboat_autoplay.py', 'plan', current}})
local plan = result and result.status == 0 and utils.parse_json(result.stdout)
if not plan then return end
local autoplay = plan.enabled
local moving, timer, remaining = false, nil, 5
local original_keep_open = mp.get_property('keep-open', 'no')
local function cancel()
    if timer then timer:kill(); timer = nil end
end
local function configure()
    mp.set_property('keep-open', autoplay and plan.next and 'yes' or original_keep_open)
    mp.set_property_native('user-data/newsboat/autoplay', autoplay)
end
local function advance(row)
    if moving then return end
    if not row then mp.osd_message('No more videos in this playlist', 3); return end
    cancel()
    moving = true
    mp.commandv('write-watch-later-config')
    local launched = mp.command_native({name='subprocess', playback_only=false,
        args={'python3', directory .. 'newsboat-play-video.py', row.url, row.title or ''}})
    if not launched or launched.status ~= 0 then
        moving = false
        mp.osd_message('Could not start the next video', 4)
    end
end
local function prompt()
    local title = (plan.next.title or plan.next.url):gsub('[\r\n]', ' ')
    mp.osd_message('Up next in ' .. remaining .. 's: ' .. title ..
        '\nShift+A: turn autoplay off    >: play now', 1.5)
end
local function countdown()
    if not autoplay or not plan.next or moving or timer then return end
    remaining = 5
    prompt()
    timer = mp.add_periodic_timer(1, function()
        remaining = remaining - 1
        if remaining <= 0 then advance(plan.next) else prompt() end
    end)
end
mp.add_forced_key_binding('A', 'newsboat-toggle-autoplay', function()
    autoplay = not autoplay
    cancel()
    local saved = mp.command_native({name='subprocess', playback_only=false,
        args={'python3', directory .. 'newsboat_autoplay.py', 'set', autoplay and 'on' or 'off'}})
    configure()
    mp.osd_message('Autoplay: ' .. (autoplay and 'ON' or 'OFF') ..
        ((not saved or saved.status ~= 0) and ' (this player only — could not save preference)' or ''), 3)
    if autoplay and mp.get_property_native('eof-reached') then countdown() end
end)
mp.add_forced_key_binding('>', 'newsboat-next-episode', function() advance(plan.next) end)
if plan.playlist then
    mp.add_forced_key_binding('<', 'newsboat-previous-episode', function() advance(plan.previous) end)
end
-- keep-open holds the last frame: eof-reached fires even without end-file.
mp.observe_property('eof-reached', 'bool', function(_, eof)
    if eof then countdown() else cancel() end
end)
mp.register_event('end-file', function(event)
    if event.reason ~= 'eof' then cancel() end
end)
mp.register_event('shutdown', cancel)
mp.register_event('file-loaded', function()
    configure()
    mp.osd_message('Autoplay: ' .. (autoplay and 'ON' or 'OFF') .. ' · Shift+A to toggle', 3)
end)
configure()
