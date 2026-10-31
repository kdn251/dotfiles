-- Pin a newly opened Newsboat player once, preserving later manual unpinning.
local utils = require 'mp.utils'
local placed = false
mp.register_event('file-loaded', function()
    if placed then return end
    placed = true
    mp.command_native_async({name='subprocess', playback_only=false,
        args={'python3', os.getenv('HOME') .. '/scripts/media_chat_fullscreen.py',
              'place', tostring(utils.getpid())},
        capture_stdout=true, capture_stderr=true}, function() end)
end)
