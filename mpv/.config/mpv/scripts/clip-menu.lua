-- Shift+C chooses a buffered clip length from 15 seconds to two minutes.
local assdraw = require 'mp.assdraw'
local utils = require 'mp.utils'
local lengths = {15, 30, 45, 60, 90, 120}
local labels = {'15 seconds', '30 seconds', '45 seconds', '1 minute', '1 minute 30 seconds', '2 minutes'}
local saving = false

local function available()
    local position = mp.get_property_number('time-pos')
    if not position then return 0 end
    local cache = mp.get_property_native('demuxer-cache-state', {})
    local ranges = cache['seekable-ranges'] or {}
    table.sort(ranges, function(a,b) return a.start < b.start end)
    local merged = {}
    for _, range in ipairs(ranges) do
        local previous = merged[#merged]
        if previous and range.start <= previous['end'] + .001 then
            previous['end'] = math.max(previous['end'], range['end'])
        else
            merged[#merged+1] = {start=range.start, ['end']=range['end']}
        end
    end
    for _, range in ipairs(merged) do
        if position >= range.start and position <= range['end'] + .25 then
            return math.max(0, position - math.max(0, range.start))
        end
    end
    return 0
end


local overlay = mp.create_osd_overlay('ass-events')
local selected, buffered, visible = 2, 0, false
local keys = {'j', 'k', 'DOWN', 'UP', 'ENTER', 'ESC', 'C'}

local function close()
    visible = false
    overlay:remove()
    for _, key in ipairs(keys) do mp.remove_key_binding('clip-menu-' .. key) end
end

local function render()
    if not visible then return end
    local width, height = mp.get_osd_size()
    if width <= 0 or height <= 0 then return end
    overlay.res_y = 720
    overlay.res_x = 720 * width / height
    local ass = assdraw.ass_new()
    ass:new_event()
    ass:pos(24, 24)
    ass:append('{\\an7\\bord0\\shad0\\1c&H201C19&\\1a&H18&}')
    ass:draw_start()
    ass:round_rect_cw(0, 0, 340, 274, 10)
    ass:draw_stop()
    local function line(y, text, color, size)
        ass:new_event()
        ass:pos(40, y)
        ass:append(string.format('{\\an7\\fnSans\\fs%d\\bord0\\shad0\\1c&H%s&}%s', size, color, text))
    end
    line(38, 'Save a clip', 'FFFFFF', 22)
    line(68, string.format('%ds buffered', buffered), 'B0B0B0', 15)
    for i, label in ipairs(labels) do
        local text = (i == selected and '>  ' or '    ') .. 'Last ' .. label
        if lengths[i] > buffered then text = text .. string.format(' (%ds available)', buffered) end
        line(96 + (i-1)*27, text, i == selected and 'C9DF82' or 'EEEEEE', 18)
    end
    line(267, 'j/k move   Enter save   Esc close', 'B0B0B0', 14)
    overlay.data = ass.text
    overlay:update()
end

local function save_selected()
    local seconds = lengths[selected]
    close()
    saving = true
    mp.osd_message('Saving clip…', 2)
    mp.command_native_async({name='subprocess', playback_only=false,
        args={os.getenv('HOME') .. '/scripts/mpv-clip.sh',
              mp.get_property('input-ipc-server', ''), tostring(utils.getpid()),
              tostring(seconds)}, capture_stdout=true, capture_stderr=true},
        function(success, result)
            saving = false
            mp.osd_message(success and result and result.status == 0 and 'Clip saved' or 'Could not save clip—see notification', 2)
        end)
end

local function open()
    if visible then close(); return end
    if saving then mp.osd_message('Saving your clip…', 2); return end
    buffered = math.floor(available())
    if buffered < 2 then mp.osd_message('Not enough buffered video yet', 2); return end
    selected, visible = 2, true
    local function move(delta)
        selected = (selected - 1 + delta) % #lengths + 1
        render()
    end
    for _, key in ipairs({'j', 'DOWN'}) do
        mp.add_forced_key_binding(key, 'clip-menu-' .. key, function() move(1) end, {repeatable=true})
    end
    for _, key in ipairs({'k', 'UP'}) do
        mp.add_forced_key_binding(key, 'clip-menu-' .. key, function() move(-1) end, {repeatable=true})
    end
    mp.add_forced_key_binding('ENTER', 'clip-menu-ENTER', save_selected)
    mp.add_forced_key_binding('ESC', 'clip-menu-ESC', close)
    mp.add_forced_key_binding('C', 'clip-menu-C', close)
    render()
end

mp.observe_property('osd-dimensions', 'native', render)
mp.register_event('file-loaded', close)
mp.add_key_binding(nil, 'open', open)
mp.register_script_message('open', open)
