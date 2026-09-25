-- Report the lifetime of this particular random pick, including local-file swaps.
local target = os.getenv('NEWSBOAT_RANDOM_LIFECYCLE')
if not target or target == '' then return end
local started = false
local function write(state)
    local file = io.open(target, 'w')
    if file then file:write(state); file:close() end
end
mp.register_event('playback-restart', function()
    if not started then started = true; write('playing') end
end)
mp.register_event('shutdown', function() write(started and 'closed' or 'failed') end)
