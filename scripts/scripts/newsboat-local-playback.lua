-- Confirm the streaming-to-local handoff only after playback resumes.
local pending

mp.register_script_message('switch', function(source, path, position, title, icon, badge)
    -- An old download must not replace a different video in a newer player.
    if mp.get_property('path', '') ~= source then return end
    pending = {path=path, title=title, icon=icon, badge=badge}
    mp.commandv('loadfile', path, 'replace', '0', 'start=' .. position)
end)

mp.register_event('playback-restart', function()
    if not pending or mp.get_property('path', '') ~= pending.path then return end
    local switched = pending
    pending = nil
    local args = {'notify-send', '-a', 'YouTube', '--app-icon', switched.badge,
                  '-t', '5000', '-u', 'low'}
    if switched.icon ~= '' then
        args[#args+1] = '-h'
        args[#args+1] = 'string:image-path:' .. switched.icon
    end
    args[#args+1] = switched.title ~= '' and switched.title or 'YouTube'
    args[#args+1] = 'Switched to the downloaded file • Playing locally'
    mp.command_native_async({name='subprocess', playback_only=false, args=args}, function() end)
end)

mp.register_event('end-file', function(event)
    if event.reason == 'error' then pending = nil end
end)
