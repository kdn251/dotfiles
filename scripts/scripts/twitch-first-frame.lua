-- Let the quality upgrade start only after the initial stream is playing.
local path = os.getenv('TWITCH_FIRST_FRAME')
local reported = false
mp.register_event('playback-restart', function()
    if reported or not path then return end
    reported = true
    local file = io.open(path, 'w')
    if file then file:write('playing'); file:close() end
end)
