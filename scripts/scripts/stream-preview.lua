-- Preview accepts a click but otherwise stays muted until explicitly promoted.
local assdraw = require 'mp.assdraw'
local spinner = mp.create_osd_overlay('ass-events')
spinner.z = 2000
local loading = true
local spin_timer
local function draw_spinner()
    if not loading then return end
    local w,h=mp.get_osd_size()
    if w<=0 or h<=0 then return end
    spinner.res_y=360
    spinner.res_x=360*w/h
    local cx,cy=spinner.res_x/2,180
    local head=math.floor(mp.get_time()*12)%12
    local a=assdraw.ass_new()
    a:new_event();a:pos(0,0)
    a:append('{\\an7\\bord0\\shad0\\1c&H000000&}')
    a:draw_start();a:rect_cw(0,0,spinner.res_x,360);a:draw_stop()
    for i=0,11 do
        local angle=(i/12)*2*math.pi-math.pi/2
        local x,y=cx+17*math.cos(angle),cy+17*math.sin(angle)
        local alpha=math.min(220,((head-i)%12)*19)
        a:new_event();a:pos(0,0)
        a:append(string.format('{\\an7\\bord0\\shad0\\1c&HFFFFFF&\\1a&H%02X&}',alpha))
        a:draw_start();a:round_rect_cw(x-2.5,y-2.5,x+2.5,y+2.5,2.5);a:draw_stop()
    end
    spinner.data=a.text;spinner:update()
end
local function stop_spinner()
    loading=false
    if spin_timer then spin_timer:kill() end
    spinner:remove()
end
spin_timer=mp.add_periodic_timer(.06,draw_spinner)
mp.observe_property('osd-dimensions','native',draw_spinner)
mp.register_event('shutdown',stop_spinner)
local marker = os.getenv('STREAM_PREVIEW_ACCEPT')
local promoted = false
local owner = os.getenv('STREAM_PREVIEW_OWNER')
mp.add_periodic_timer(.5,function()
    if promoted or not owner then return end
    local f=io.open('/proc/' .. owner .. '/stat','r')
    if f then f:close() else mp.commandv('quit') end
end)
mp.add_forced_key_binding('MBTN_LEFT','preview-accept',function()
    local f = marker and io.open(marker,'w')
    if f then f:write('accept');f:close() end
end)
mp.register_script_message('preview-promote',function(session, page, title, marker_path)
    promoted = true
    stop_spinner()
    mp.set_property('idle','no')
    mp.remove_key_binding('preview-accept')
    mp.set_property_native('mute',false)
    mp.set_property_native('pause',false)
    mp.set_property_native('user-data/stream-page',page)
    mp.set_property_native('user-data/stream-ready-session',session)
    mp.set_property('force-media-title',title)
    if marker_path and marker_path~='' then
        local f=io.open(marker_path,'w');if f then f:write('playing');f:close() end
    end
    mp.osd_message('',0)
end)
mp.register_event('playback-restart',function()
    stop_spinner()
    mp.set_property_native('user-data/preview-ready',true)
    mp.osd_message('',0)
end)
mp.register_event('end-file',function(event)
    if event.reason=='error' and not promoted then
        stop_spinner()
        mp.commandv('quit')
    end
end)
