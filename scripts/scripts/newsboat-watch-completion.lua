-- Track completion of explicit local downloads, including very short videos.
local helper = os.getenv('NEWSBOAT_MAINTENANCE')
local url = os.getenv('NEWSBOAT_MEDIA_URL')
if not helper or not url then return end
local loaded = false
local restored = false
local reported = false
local path = ''
local position, duration
local last_position, last_duration
local utils = require('mp.utils')
local function save_progress(completed)
    if not loaded and completed ~= true then return end
    -- Read the latest seek position even if its observer callback is queued.
    duration = mp.get_property_number('duration') or duration
    completed = completed == true or mp.get_property_native('eof-reached') == true
    if completed then
        position = duration
    else
        position = mp.get_property_number('time-pos') or position
    end
    if not position or not duration or duration <= 0 then return end
    if position == last_position and duration == last_duration then return end
    -- Snapshot before exiting; the detached worker may wait for the library
    -- lock without keeping the video window open. Each snapshot has its own
    -- timestamp so late workers cannot overwrite a newer position or reset.
    local snapshot = os.tmpname()
    local file = io.open(snapshot, 'w')
    if not file then return end
    file:write(utils.format_json({url=url, position=position, duration=duration}))
    file:close()
    local saved = mp.command_native({name='subprocess', playback_only=false, detach=true,
        args={'python3', helper, 'progress-file', snapshot}})
    if saved and saved.status == 0 then
        last_position, last_duration = position, duration
    else
        os.remove(snapshot)
    end
end
mp.observe_property('time-pos', 'number', function(_, value)
    if value then position = value end
end)
mp.observe_property('duration', 'number', function(_, value)
    if value and value > 0 then duration = value end
end)
mp.add_periodic_timer(5, save_progress)
-- Save before mpv clears time-pos/duration during close or loadfile replacement.
mp.add_hook('on_unload', 50, function()
    save_progress(mp.get_property_native('eof-reached') == true)
    loaded = false
end)
mp.register_event('end-file', function(event)
    if event.reason == 'eof' then save_progress(true) end
end)
mp.register_event('shutdown', save_progress)
-- keep-open holds the last frame without sending end-file during the countdown.
mp.observe_property('eof-reached', 'bool', function(_, eof)
    if eof and loaded then save_progress(true) end
end)
-- Fetch resume state while MPV resolves/opens the media, rather than starting
-- another Python process after the network work has finished.
local resume_job, resume_request, resume_result, resume_waiter
local resume_generation = 0
local function current_url()
    local value = mp.get_property_native('user-data/newsboat/url', '')
    return value ~= '' and value or url
end
local function prefetch_resume()
    local next_url = current_url()
    if (restored and next_url == url) or resume_request == next_url then return end
    if resume_job then mp.abort_async_command(resume_job) end
    resume_request, resume_result = next_url, nil
    resume_generation = resume_generation + 1
    local generation = resume_generation
    resume_job = mp.command_native_async({name='subprocess', playback_only=false,
        capture_stdout=true, capture_stderr=true, args={'python3', helper, 'resume-spec', next_url}},
        function(ok, result)
            if generation ~= resume_generation then return end
            resume_job = nil
            resume_result = {ok=ok and result and result.status == 0,
                spec=result and (result.stdout or ''):gsub('%s+$', '') or ''}
            if resume_waiter then local finish=resume_waiter; resume_waiter=nil; finish() end
        end)
end
mp.add_hook('on_load', 5, prefetch_resume)
mp.add_hook('on_preloaded', 50, function(hook)
    local next_url = current_url()
    if next_url ~= url then
        url = next_url; restored = false
        position, duration, last_position, last_duration = nil, nil, nil, nil
    end
    -- A streaming-to-local handoff supplies its own position.
    if restored then return end
    prefetch_resume()
    local function apply_resume()
        restored = true
        local total = mp.get_property_number('duration', 0)
        local resume
        if resume_result and resume_result.ok then
            local spec = resume_result.spec
            local percent = spec:match('^([%d.]+)%%$')
            resume = percent and tonumber(percent) * total / 100 or tonumber(spec)
        else
            -- Compatibility/error fallback; normal startup uses the prefetched result.
            local result = mp.command_native({name='subprocess', playback_only=false,
                capture_stdout=true, args={'python3', helper, 'resume', url, tostring(total)}})
            resume = result and result.status == 0 and tonumber(result.stdout)
        end
        if resume and resume >= 0 then
            if total > 0 then resume = math.min(resume, math.max(0, total - .5)) end
            mp.set_property('file-local-options/start', tostring(resume))
        end
    end
    if resume_job then
        hook:defer()
        resume_waiter = function() apply_resume(); hook:cont() end
    else
        apply_resume()
    end
end)
mp.register_event('file-loaded', function()
    loaded = true
    position = mp.get_property_number('time-pos')
    duration = mp.get_property_number('duration')
    reported = false
    path = mp.get_property('path', '')
end)
mp.observe_property('percent-pos', 'number', function(_, percent)
    if reported or not percent or percent < 90 or path:sub(1,1) ~= '/' then return end
    reported = true
    -- Completion bookkeeping must not block playback or window closing.
    mp.command_native({name='subprocess', playback_only=false, detach=true,
        args={'python3', helper, 'watched', path, url, tostring(percent / 100)}})
end)
