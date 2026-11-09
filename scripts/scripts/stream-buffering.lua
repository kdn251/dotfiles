-- Temporary network stalls retain MPV's decoded frame; draw only an indicator.
local assdraw = require 'mp.assdraw'
local overlay = mp.create_osd_overlay('ass-events')
overlay.z = 1900
local stalled_at = nil
local played = false
local function clear()
    stalled_at = nil
    overlay:remove()
end
local function draw()
    local buffering = played and mp.get_property_native('paused-for-cache', false)
        and not mp.get_property_native('pause', false)
        and not mp.get_property_native('eof-reached', false)
    if not buffering then clear(); return end
    stalled_at = stalled_at or mp.get_time()
    -- The GTK pane owns this indicator during multi-view.
    if mp.get_property_native('user-data/stream-multiview', false)
        or mp.get_time()-stalled_at < .5 then overlay:remove(); return end
    local w,h = mp.get_osd_size()
    if w<=0 or h<=0 then return end
    overlay.res_x=w; overlay.res_y=h
    local a=assdraw.ass_new()
    a:new_event(); a:pos(0,0)
    a:append('{\\an7\\bord0\\shad0\\1c&HFFFFFF&}')
    local angle=mp.get_time()*2*math.pi
    a:draw_start()
    for i=0,39 do
        local t=angle+i/40*math.pi*1.5
        local t2=angle+(i+1)/40*math.pi*1.5
        a:move_to(w/2+12*math.cos(t),h/2+12*math.sin(t))
        a:line_to(w/2+15*math.cos(t),h/2+15*math.sin(t))
        a:line_to(w/2+15*math.cos(t2),h/2+15*math.sin(t2))
        a:line_to(w/2+12*math.cos(t2),h/2+12*math.sin(t2))
    end
    a:draw_stop(); overlay.data=a.text; overlay:update()
end
mp.observe_property('paused-for-cache','bool',draw)
mp.observe_property('pause','bool',draw)
mp.register_event('start-file',function() played=false;clear() end)
mp.register_event('playback-restart',function() played=true;clear() end)
mp.register_event('end-file',function() played=false;clear() end)
mp.register_event('shutdown',clear)
mp.add_periodic_timer(1/30,draw)
