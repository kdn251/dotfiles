-- Advance through the originating Newsboat playlist, retaining normal playback
-- helpers (local-file lookup, resume, progress tracking, and notifications).
local utils = require('mp.utils')
local script_directory = utils.split_path(debug.getinfo(1, 'S').source:sub(2))
local context = os.getenv('NEWSBOAT_PLAYLIST_CONTEXT')
local current = os.getenv('NEWSBOAT_MEDIA_URL')
if not context or not current then return end
local file = io.open(context, 'r')
if not file then return end
local data = utils.parse_json(file:read('*a'))
file:close()
if not data or type(data.rows) ~= 'table' then return end
local rows, index = {}, nil
for _, row in ipairs(data.rows) do
    if type(row.url) == 'string' and row.url:match('^https?://') then
        rows[#rows + 1] = row
        if row.url == current then index = #rows end
    end
end
if not index then return end
local moving = false
local function advance(offset, automatic)
    if moving then return end
    local row = rows[index + offset]
    if not row then
        if not automatic then mp.osd_message(offset > 0 and 'Last video in playlist' or 'First video in playlist') end
        return
    end
    moving = true
    -- The detached launcher starts a fresh player so each episode gets its own
    -- source URL, resume state and stream-to-local handoff. It closes this player.
    mp.commandv('write-watch-later-config')
    local result = mp.command_native({name='subprocess', playback_only=false,
        args={'python3', script_directory .. 'newsboat-play-video.py', row.url, row.title or ''}})
    if not result or result.status ~= 0 then
        moving = false
        mp.osd_message('Could not start the next playlist video')
    end
end
mp.add_forced_key_binding('>', 'newsboat-next-episode', function() advance(1, false) end)
mp.add_forced_key_binding('<', 'newsboat-previous-episode', function() advance(-1, false) end)
mp.register_event('end-file', function(event)
    -- Stop/quit, playback errors, and swapping onto a local copy aren't EOF.
    if event.reason == 'eof' then advance(1, true) end
end)
