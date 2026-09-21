-- Report playback success once, not just successful URL extraction/loading.
local target = os.getenv('NEWSBOAT_PLAY_READY')
if not target or target == '' then return end
local reported = false
local function report(value)
    if reported then return end
    reported = true
    local file = io.open(target, 'w')
    if file then file:write(value); file:close() end
end
mp.register_event('playback-restart', function() report('playing') end)
mp.register_event('end-file', function() report('failed') end)
mp.register_event('shutdown', function() report('failed') end)
