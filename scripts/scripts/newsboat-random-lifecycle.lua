-- Report the lifetime of this particular random pick, including local-file swaps.
local target = os.getenv('NEWSBOAT_RANDOM_LIFECYCLE')
if not target or target == '' then return end
local started, closed = false, false
local original = os.getenv("NEWSBOAT_MEDIA_URL")
local function write(state)
    local file = io.open(target, 'w')
    if file then file:write(state); file:close() end
end
mp.register_event('playback-restart', function()
    if closed then return end
    if not started then started = true; write('playing') end
end)
mp.register_event('file-loaded', function()
    local current = mp.get_property_native('user-data/newsboat/url', original)
    if current ~= original and not closed then
        closed = true; write(started and 'closed' or 'failed')
    end
end)
mp.register_event('shutdown', function()
    if not closed then write(started and 'closed' or 'failed') end
end)
