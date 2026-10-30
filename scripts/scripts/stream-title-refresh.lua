-- Metadata updates run outside the player; they never reload or seek media.
local service = os.getenv('STREAM_TITLE_SERVICE') or 'Twitch'
local initial_name = os.getenv('STREAM_TITLE_NAME') or ''
local helper = (os.getenv('HOME') or '') .. '/scripts/stream-title-refresh.py'
local generation = 0
local pending = nil
local function name()
    service = mp.get_property_native('user-data/stream-service', service)
    local current = mp.get_property_native('user-data/stream-name', '')
    if current ~= '' then return current end
    if service == 'Twitch' then
        return mp.get_property_native('user-data/twitch-channel', '')
    end
    return initial_name
end
local function refresh()
    local channel = name()
    if channel == '' or pending then return end
    local version = generation
    local requested_service = service
    pending = mp.command_native_async({name='subprocess', playback_only=false,
        args={'python3', helper, channel, service}, capture_stdout=true,
        capture_stderr=true}, function(success, result)
        pending = nil
        if not success or not result or result.status ~= 0 or
           version ~= generation or channel ~= name() or requested_service ~= service then return end
        local title = (result.stdout or ''):gsub('%s+$', '')
        if title ~= '' and title ~= mp.get_property('force-media-title', '') then
            mp.set_property('force-media-title', title)
        end
    end)
end
mp.observe_property('user-data/stream-name', 'string', function()
    generation = generation + 1
end)
-- Give playback first priority on startup; later changes arrive within a minute.
mp.add_timeout(5, refresh)
mp.add_periodic_timer(60, refresh)
mp.register_event('shutdown', function()
    if pending then mp.abort_async_command(pending) end
end)
