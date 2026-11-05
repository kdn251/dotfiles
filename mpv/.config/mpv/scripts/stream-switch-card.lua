-- A brief destination card for live-stream back/forward navigation.
local assdraw = require 'mp.assdraw'
local overlay = mp.create_osd_overlay('ass-events')
overlay.z = 1500
local card, generation, timer = nil, 0, nil
local function hide()
    generation=generation+1
    card=nil
    overlay:remove()
    mp.commandv('overlay-remove',44)
    if timer then timer:kill();timer=nil end
end
local function escape(text)
    return text:gsub('\\','\\\239\187\191'):gsub('{','\\{'):gsub('}','\\}'):gsub('[\r\n]',' ')
end
local function draw()
    if not card then return end
    local w,h=mp.get_osd_size()
    if w<=0 or h<=0 then return end
    local scale=math.min(1,h/720)
    overlay.res_y=h/scale;overlay.res_x=w/scale
    local width=math.min(400,overlay.res_x-32)
    local x,y,height=16,16,96
    if mp.get_property_bool('fullscreen',false) then
        local layout=mp.get_property_native('user-data/media-panel-layout',{})
        local left=(layout.left or 0)*overlay.res_x
        local right=(1-(layout.right or 0))*overlay.res_x
        width=math.min(width,math.max(1,right-left-32))
        x=left+(right-left-width)/2
        local dimensions=mp.get_property_native('osd-dimensions',{})
        -- Anchor to the rendered video's top edge, including theater letterboxing.
        -- If there is no room above the video, keep the card inside the screen.
        y=math.max(12,(dimensions.mt or 0)/scale-height-10)
    end
    local a=assdraw.ass_new()
    a:new_event();a:pos(0,0)
    a:append('{\\an7\\bord0\\shad0\\1c&H242424&\\1a&H18&}')
    a:draw_start();a:round_rect_cw(x,y,x+width,y+height,8);a:draw_stop()
    a:new_event();a:pos(x+90,y+12)
    a:append('{\\an7\\fs20\\bord0\\shad0\\1c&HBFC8CD&}'..escape(card.label))
    a:new_event();a:pos(x+90,y+44)
    a:append(string.format('{\\an7\\fs28\\b1\\bord0\\shad0\\1c&HFFFFFF&\\clip(%.0f,%.0f,%.0f,%.0f)}',x+90,y,x+width-12,y+height)..escape(card.name))
    overlay.data=a.text;overlay:update()
    if card.path then
        local size=math.floor(66*scale)
        mp.command_native({'overlay-add',44,math.floor((x+12)*scale),math.floor((y+15)*scale),
            card.path,0,'bgra',96,96,384,size,size})
    end
end
mp.register_script_message('stream-switch-card',function(service,name,label)
    hide()
    local version=generation
    card={name=name,label=label or 'Switching stream'}
    draw()
    timer=mp.add_timeout(2.5,hide)
    mp.command_native_async({name='subprocess',playback_only=false,
        args={'python3',os.getenv('HOME')..'/scripts/stream-title-avatar.py',service,name},
        capture_stdout=true,capture_stderr=true},function(ok,result)
        if version~=generation or not card or not ok or not result or result.status~=0 then return end
        local path=result.stdout:gsub('%s+$','')
        if path~='' then card.path=path;draw() end
    end)
end)
mp.observe_property('osd-dimensions','native',draw)
mp.observe_property('fullscreen','bool',draw)
mp.observe_property('user-data/media-panel-layout','native',draw)
mp.register_event('shutdown',hide)
