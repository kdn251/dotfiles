-- Metadata updates run outside the player; they never reload or seek media.
local service = os.getenv('STREAM_TITLE_SERVICE') or 'Twitch'
local initial_name = os.getenv('STREAM_TITLE_NAME') or ''
local helper = (os.getenv('HOME') or '') .. '/scripts/stream-title-refresh.py'
local generation = 0
local pending = nil
local clock_title, clock_seconds, clock_at, clock_channel, clock_service

local function name()
    service = mp.get_property_native('user-data/stream-service', service)
    local current = mp.get_property_native('user-data/stream-name', '')
    if current ~= '' then return current end
    if service == 'Twitch' then
        return mp.get_property_native('user-data/twitch-channel', '')
    end
    return initial_name
end
local function tick_uptime()
    if not clock_title or clock_channel ~= name() or clock_service ~= service then return end
    local seconds = clock_seconds + math.floor(mp.get_time() - clock_at)
    local clock = string.format('%d:%02d:%02d', math.floor(seconds / 3600),
        math.floor(seconds / 60) % 60, seconds % 60)
    local heading, tail = clock_title:match('^(.-)( | .*)$')
    heading, tail = heading or clock_title, tail or ''
    local title = heading:gsub('%d+:%d%d:%d%d$', clock) .. tail
    if title ~= mp.get_property('force-media-title', '') then
        mp.set_property('force-media-title', title)
    end
end
mp.add_periodic_timer(1, tick_uptime)
local refresh
refresh = function()
    local channel = name()
    if channel == '' or pending then return end
    local version = generation
    local requested_service = service
    pending = mp.command_native_async({name='subprocess', playback_only=false,
        args={'python3', helper, channel, service}, capture_stdout=true,
        capture_stderr=true}, function(success, result)
        pending = nil
        if version ~= generation or channel ~= name() or requested_service ~= service then
            mp.add_timeout(0, refresh)
            return
        end
        if not success or not result or result.status ~= 0 then return end
        local title = (result.stdout or ''):gsub('%s+$', '')
        local heading = title:match('^(.-) | ') or title
        local hours, minutes, seconds = heading:match(' (%d+):(%d%d):(%d%d)$')
        clock_title = nil
        if hours then
            clock_title, clock_seconds, clock_at = title, tonumber(hours)*3600 + tonumber(minutes)*60 + tonumber(seconds), mp.get_time()
            clock_channel, clock_service = channel, requested_service
        end
        if title ~= '' and title ~= mp.get_property('force-media-title', '') then
            mp.set_property('force-media-title', title)
        end
    end)
end
mp.observe_property('user-data/stream-name', 'string', function()
    clock_title = nil
    generation = generation + 1
    local version = generation
    mp.add_timeout(0.2, function()
        if version == generation then refresh() end
    end)
end)
-- Fetch missing metadata asynchronously on startup and every stream switch.
mp.add_timeout(0.2, refresh)
mp.add_periodic_timer(60, refresh)
mp.register_event('shutdown', function()
    if pending then mp.abort_async_command(pending) end
end)
