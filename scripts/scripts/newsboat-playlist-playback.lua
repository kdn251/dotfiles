-- Switch videos inside this player, preserving the window and per-video context.
local utils = require('mp.utils')
local directory = utils.split_path(debug.getinfo(1, 'S').source:sub(2))
local current = os.getenv('NEWSBOAT_MEDIA_URL')
if not current then return end
local result = mp.command_native({name='subprocess', playback_only=false, capture_stdout=true,
    args={'python3', directory .. 'newsboat_autoplay.py', 'plan', current}})
local plan = result and result.status == 0 and utils.parse_json(result.stdout)
if not plan then return end
local startup_queue_token = plan.current_queue_token
-- Completed videos leave the live queue. Retain this player's completed count
-- so a three-video run advances 1/3, 2/3, 3/3 rather than 1/3, 1/2, 1/1.
local completed_queue = {}
local function queue_position(up_next)
    local live, completed = {}, 0
    for _, token in ipairs(plan.queue_tokens or {}) do live[token] = true end
    for token, _ in pairs(completed_queue) do
        if not live[token] then completed = completed + 1 end
    end
    local position = plan.queue_position
    if up_next then position = plan.next_queue_position end
    if position then return position.number + completed, position.total + completed end
    if not up_next and startup_queue_token and completed_queue[startup_queue_token] then
        return completed_queue[startup_queue_token], #(plan.queue_tokens or {}) + completed
    end
end
local function episode_label(up_next)
    local number, total = queue_position(up_next)
    if number then return string.format('Queue video %d of %d', number, total) end
    local episode = plan.episode
    if up_next then episode = plan.next_episode end
    return episode and string.format('Episode %d of %d', episode.number, episode.total) or nil
end
local updating_title = false
local function update_episode_title()
    if updating_title then return end
    local label = episode_label()
    local title = mp.get_property('media-title', '')
    if title == '' then return end
    local plain = title:gsub('^Episode %d+ of %d+ · ', ''):gsub('^Queue video %d+ of %d+ · ', '')
    local desired = label and (label .. ' · ' .. plain) or plain
    if desired ~= title then
        updating_title = true
        mp.set_property('force-media-title', desired)
        updating_title = false
    end
end
mp.observe_property('media-title', 'string', update_episode_title)
local autoplay = plan.enabled
local plan_job, queue_watcher, switch_job
local reported_playing, reported_finished = false, false
local switched_in_place = false
local loading_title
local play_on_load = false
local moving, timer, remaining = false, nil, 5
mp.set_property_native('user-data/newsboat/url', current)
local original_idle = mp.get_property('idle', 'no')
local original_keep_open = mp.get_property('keep-open', 'no')
-- Keep this separate from thumbfast's seek-preview overlay (42).
local thumbnail_id = 61
local thumbnail, thumbnail_job, thumbnail_requested
local thumbnail_visible = false
local function hide_thumbnail()
    if thumbnail_visible then mp.commandv('overlay-remove', thumbnail_id) end
    thumbnail_visible = false
end
local function show_thumbnail()
    if not timer or not thumbnail then return end
    local width, height = mp.get_osd_size()
    if not width or not height or width < 1 or height < 1 then return end
    -- Leave the upper third clear for the countdown, title and controls.
    local scale = math.min(width * .75 / thumbnail.width, height * .50 / thumbnail.height)
    local w, h = math.max(1, math.floor(thumbnail.width * scale)), math.max(1, math.floor(thumbnail.height * scale))
    local x, y = math.floor((width-w)/2), math.floor(height * .38)
    mp.command_native({'overlay-add', thumbnail_id, x, y, thumbnail.path, 0,
        'bgra', thumbnail.width, thumbnail.height, thumbnail.width*4, w, h})
    thumbnail_visible = true
end
local function prepare_thumbnail()
    if thumbnail_requested or not autoplay or not plan.next then return end
    thumbnail_requested = true
    thumbnail_job = mp.command_native_async({name='subprocess', playback_only=false, capture_stdout=true,
        args={'python3', directory .. 'newsboat-up-next-thumbnail.py', plan.next.url}},
        function(success, response)
            thumbnail_job = nil
            if success and response and response.status == 0 then
                local image = utils.parse_json(response.stdout)
                if image and type(image.path) == 'string' and image.width == 480 and image.height == 270 then
                    thumbnail = image
                    show_thumbnail()
                end
            end
        end)
end
mp.observe_property('osd-dimensions', 'native', show_thumbnail)
local function cancel()
    if timer then timer:kill(); timer = nil end
    hide_thumbnail()
end
local function configure()
    mp.set_property('keep-open', autoplay and plan.next and 'yes' or original_keep_open)
    mp.set_property_native('user-data/newsboat/autoplay', autoplay)
    prepare_thumbnail()
end
local function advance(row, automatic)
    if moving then return end
    if not row then mp.osd_message(plan.queue and 'No more videos in this queue direction' or 'No more videos in this playlist', 3); return end
    local should_play = automatic or mp.get_property_native('eof-reached') == true
    cancel()
    moving = true
    loading_title = row.title or row.url
    mp.osd_message('Loading: ' .. loading_title, 3600)
    -- Resolve local copies without destroying the current window or blocking UI.
    switch_job = mp.command_native_async({name='subprocess', playback_only=false, capture_stdout=true,
        args={'python3', directory .. 'newsboat-playback-target.py', row.url, row.title or '',
              row.queue_token and 'queue' or 'normal'}}, function(success, response)
        switch_job = nil
        local target = success and response and response.status == 0 and utils.parse_json(response.stdout)
        if not target or not target.path or not target.plan then
            moving = false; loading_title = nil
            mp.osd_message('Could not load the next video', 4)
            return
        end
        mp.commandv('write-watch-later-config')
        if plan_job then mp.abort_async_command(plan_job); plan_job = nil end
        if thumbnail_job then mp.abort_async_command(thumbnail_job); thumbnail_job = nil end
        hide_thumbnail(); thumbnail, thumbnail_requested = nil, nil
        current, plan = target.url, target.plan
        startup_queue_token = plan.current_queue_token
        reported_playing, reported_finished = false, false
        switched_in_place = true
        mp.set_property_native('user-data/newsboat/url', current)
        mp.set_property('force-window', 'yes')
        mp.set_property('idle', 'yes')
        mp.set_property('force-media-title', target.title or '')
        mp.set_property('cache', target['local'] and 'no' or 'yes')
        mp.set_property('ytdl-format', 'bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best')
        play_on_load = should_play
        mp.commandv('loadfile', target.path, 'replace')
    end)
end
local function prompt()
    local title = (plan.next.title or plan.next.url):gsub('[\r\n]', ' ')
    local next_label = episode_label(true)
    local current_label = episode_label(false)
    mp.osd_message((current_label and 'Watching: ' .. current_label .. '\n' or '') ..
        'Up next in ' .. remaining .. 's: ' .. (next_label and next_label .. ' · ' or '') .. title ..
        '\nShift+A: turn autoplay off    >: play now', 1.5)
end
local function countdown()
    if not autoplay or not plan.next or moving or timer then return end
    remaining = 5
    prompt()
    timer = mp.add_periodic_timer(1, function()
        remaining = remaining - 1
        if remaining <= 0 then advance(plan.next, true) else prompt() end
    end)
    show_thumbnail()
end
-- The queue can change while this player is open. Read a tiny local status
-- file; only invoke Python when membership changes, never on every tick.
local queue_path = os.getenv('NEWSBOAT_QUEUE_STATUS') or
    ((os.getenv('XDG_STATE_HOME') or (os.getenv('HOME') .. '/.local/state')) .. '/newsboat/viewing-queue.tsv')
local function queue_version()
    local file = io.open(queue_path, 'r')
    if not file then return '' end
    local value = file:read('*a'); file:close(); return value
end
local queue_seen = queue_version()
local function refresh_queue()
    if moving or plan_job then return end
    local version = queue_version()
    if version == queue_seen then return end
    plan_job = mp.command_native_async({name='subprocess', playback_only=false, capture_stdout=true,
        args={'python3', directory .. 'newsboat_autoplay.py', 'plan', current, plan.queue and 'on' or 'off'}},
        function(success, response)
            plan_job = nil
            if not success or not response or response.status ~= 0 then return end
            local updated = utils.parse_json(response.stdout)
            if not updated then return end
            queue_seen = version
            local old_next = plan.next and (plan.next.queue_token or plan.next.url)
            local new_next = updated.next and (updated.next.queue_token or updated.next.url)
            plan = updated
            update_episode_title()
            if old_next ~= new_next then
                cancel()
                if thumbnail_job then mp.abort_async_command(thumbnail_job); thumbnail_job = nil end
                thumbnail, thumbnail_requested = nil, nil
                configure()
                if autoplay and mp.get_property_native('eof-reached') then countdown() end
            end
        end)
end
queue_watcher = mp.add_periodic_timer(.5, refresh_queue)
mp.register_event('playback-restart', function()
    if reported_playing then return end
    reported_playing = true
    if switched_in_place then
        moving = false; loading_title = nil
        mp.set_property('idle', original_idle)
        mp.osd_message('', 0)
        mp.command_native({name='subprocess', playback_only=false, detach=true,
            args={'python3', directory .. 'newsboat-playback-started.py', current}})
    end
    if startup_queue_token and startup_queue_token ~= '' then
        mp.command_native_async({name='subprocess', playback_only=false,
            args={'python3', directory .. 'newsboat_queue.py', 'started', current, startup_queue_token}},
            function() refresh_queue() end)
    end
end)
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
mp.add_forced_key_binding('>', 'newsboat-next-episode', function()
    if plan.queue then advance(plan.queue_next) else advance(plan.next) end
end)
mp.add_forced_key_binding('<', 'newsboat-previous-episode', function() advance(plan.previous) end)
local function finish_queue_item()
    if reported_finished or not startup_queue_token or startup_queue_token == '' then return end
    reported_finished = true
    local number = queue_position(false)
    if number then completed_queue[startup_queue_token] = number end
    -- Detached so natural EOF followed by player shutdown cannot cancel removal.
    mp.command_native({name='subprocess', playback_only=false, detach=true,
        args={'python3', directory .. 'newsboat_queue.py', 'finished', current, startup_queue_token}})
end
-- keep-open holds the last frame: eof-reached fires even without end-file.
mp.observe_property('eof-reached', 'bool', function(_, eof)
    if eof then finish_queue_item(); countdown() else cancel() end
end)
mp.register_event('end-file', function(event)
    if event.reason == 'eof' then finish_queue_item() else cancel() end
    if event.reason == 'error' then
        play_on_load = false
        moving = false; loading_title = nil
        mp.osd_message('Could not load video — use < or > to choose another', 6)
    end
end)
mp.register_event('shutdown', function()
    cancel()
    if thumbnail_job then mp.abort_async_command(thumbnail_job) end
    if plan_job then mp.abort_async_command(plan_job) end
    if switch_job then mp.abort_async_command(switch_job) end
    if queue_watcher then queue_watcher:kill() end
end)
mp.register_event('file-loaded', function()
    if play_on_load then
        -- keep-open pauses at EOF; the replacement must not inherit that pause.
        mp.set_property_native('pause', false)
        play_on_load = false
    end
    configure()
    update_episode_title()
    if not loading_title then mp.osd_message((episode_label() and episode_label() .. ' · ' or '') .. 'Autoplay: ' .. (autoplay and 'ON' or 'OFF') .. ' · Shift+A to toggle', 3) end
end)
configure()
