-- Centered Queue picker. Loaded by the existing Newsboat playback controller.
local mp = require('mp')
local utils = require('mp.utils')
local assdraw = require('mp.assdraw')
local M = {}
function M.new(directory, current, choose, opened, closed)
    local visible, rows, selected, job, timer = false, {}, 1, nil, nil
    local overlay = mp.create_osd_overlay('ass-events')
    overlay.z = 1000
    local bindings = {}
    local message = 'Loading queue…'
    local thumbnails, image_jobs, image_count, generation = {}, {}, 0, 0
    local draw
    local displayed, resize_timer = {}, nil
    local function clear_images()
        for id in pairs(displayed) do mp.commandv('overlay-remove',id) end
        displayed={}
    end
    local function request_image(url)
        if thumbnails[url] ~= nil or image_jobs[url] or image_count >= 2 then return end
        local epoch = generation
        image_count=image_count+1
        image_jobs[url]=mp.command_native_async({name='subprocess',playback_only=false,capture_stdout=true,
            args={'python3',directory..'newsboat-up-next-thumbnail.py',url,'--queue'}},function(ok,result)
            if epoch ~= generation then return end
            image_jobs[url]=nil;image_count=image_count-1
            if not visible then return end
            local image=ok and result and result.status==0 and utils.parse_json(result.stdout)
            thumbnails[url]=(image and type(image.path)=='string' and image.width==384 and image.height==216) and image or false
            draw()
        end)
    end
    local function clean(text, limit)
        text = tostring(text or ''):gsub('[\r\n\t]', ' '):gsub('\\', '/'):gsub('{', '｛'):gsub('}', '｝')
        local chars = {}
        for c in text:gmatch('[%z\1-\127\194-\244][\128-\191]*') do chars[#chars+1] = c end
        if #chars > limit then
            while #chars > limit-1 do table.remove(chars) end
            chars[#chars+1] = '…'
        end
        return table.concat(chars)
    end
    draw = function()
        if not visible then return end
        local w,h = mp.get_osd_size()
        if not w or not h or h == 0 then return end
        local width = 720*w/h
        local panel = math.min(1000,width-36)
        local x = (width-panel)/2
        local shown = math.min(7,math.max(1,#rows))
        local height = 114+shown*66
        local top = (720-height)/2
        local a = assdraw.ass_new()
        local function box(l,t,r,b,color,alpha)
            a:new_event();a:append('{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H'..color..'&\\1a&H'..(alpha or '00')..'&}')
            a:draw_start();a:rect_cw(l,t,r,b);a:draw_stop()
        end
        local function text(px,py,size,color,value)
            a:new_event();a:append(string.format('{\\an7\\pos(%f,%f)\\fnSans\\fs%d\\bord0\\shad0\\1c&H%s&}',px,py,size,color))
            a:append(value)
        end
        box(0,0,width,720,'000000','88')
        box(x-1,top-1,x+panel+1,top+height+1,'807060')
        box(x,top,x+panel,top+height,'2E1E1E')
        text(x+22,top+14,26,'F4D6CD','Queue')
        text(x+panel-145,top+20,16,'C2ADA6',#rows..' videos')
        local start = math.max(1,math.min(selected-3,#rows-shown+1))
        local limit = math.max(8,math.floor((panel-245)/12))
        local needed = {}
        if #rows == 0 then text(x+22,top+65,21,'C2ADA6',message) end
        for i=start,math.min(#rows,start+shown-1) do
            local row = rows[i]
            local y = top+54+(i-start)*66
            if i==selected then box(x+10,y,x+panel-10,y+61,'655032') end
            local image = thumbnails[row.url]
            if image then
                local scale=h/720
                local id = 40+i-start
                local command = {'overlay-add',id,math.floor((x+22)*scale),math.floor((y+3)*scale),
                    image.path,0,'bgra',image.width,image.height,image.width*4,
                    math.max(1,math.floor(96*scale)),math.max(1,math.floor(54*scale))}
                local signature = table.concat(command,'|')
                needed[id]=signature
                if displayed[id]~=signature then mp.command_native(command) end
            else
                box(x+22,y+3,x+118,y+57,'382828')
                text(x+28,y+23,11,'C2ADA6',image==false and 'No thumbnail' or 'Loading…')
                request_image(row.url)
            end
            local playing = row.url == current()
            local pct = row.percent or 0
            if playing then pct = math.floor(mp.get_property_number('percent-pos',pct)) end
            text(x+132,y+6,20,playing and 'DEC294' or 'F4D6CD',
                (playing and '▶ ' or '')..i..'. '..clean(row.title or row.url,limit))
            text(x+132,y+34,16,'C2ADA6',clean(row.source or '',limit)..'  ·  '..pct..'% watched')
        end
        text(x+22,top+height-27,15,'C2ADA6','j/k or ↑/↓  Browse     Enter  Play     Esc / Shift+W  Close')
        for id in pairs(displayed) do
            if not needed[id] then mp.commandv('overlay-remove',id) end
        end
        displayed=needed
        overlay.res_x,overlay.res_y,overlay.data = width,720,a.text
        overlay:update()
    end
    local function refresh()
        if job or not visible then return end
        job = mp.command_native_async({name='subprocess',playback_only=false,capture_stdout=true,
            args={'python3',directory..'newsboat_queue.py','menu-json'}},function(ok,result)
            job=nil
            if not visible then return end
            local updated = ok and result and result.status==0 and utils.parse_json(result.stdout)
            if updated then
                local wanted = rows[selected] and rows[selected].queue_token
                rows=updated
                selected=math.min(selected,math.max(1,#rows))
                for i,row in ipairs(rows) do
                    if (wanted and row.queue_token==wanted) or (not wanted and row.url==current()) then selected=i;break end
                end
                message='Your queue is empty'
            else message='Could not load queue' end
            draw()
        end)
    end
    local function close(silent)
        if not visible then return end
        visible=false
        if resize_timer then resize_timer:kill();resize_timer=nil end
        generation=generation+1
        for _,id in pairs(image_jobs) do mp.abort_async_command(id) end
        image_jobs={};image_count=0;clear_images()
        if job then mp.abort_async_command(job);job=nil end
        if timer then timer:kill();timer=nil end
        for _,name in ipairs(bindings) do mp.remove_key_binding(name) end
        bindings={};overlay:remove()
        if closed and not silent then closed() end
    end
    local function bind(key,name,fn,repeatable)
        name='newsboat-queue-menu-'..name
        bindings[#bindings+1]=name
        mp.add_forced_key_binding(key,name,fn,{repeatable=repeatable or false})
    end
    local function move(delta) selected=math.max(1,math.min(#rows,selected+delta));draw() end
    local function toggle()
        if visible then close();return end
        visible=true;rows={};selected=1;message='Loading queue…'
        for url,image in pairs(thumbnails) do if image==false then thumbnails[url]=nil end end
        if opened then opened() end
        bind('j','down',function() move(1) end,true)
        bind('k','up',function() move(-1) end,true)
        bind('DOWN','arrow-down',function() move(1) end,true)
        bind('UP','arrow-up',function() move(-1) end,true)
        bind('W','toggle',close)
        bind('ESC','close',close)
        bind('q','dismiss',close)
        bind('ENTER','play',function()
            local row=rows[selected]
            if not row then return end
            close()
            if row.url~=current() then choose(row) end
        end)
        draw();refresh();timer=mp.add_periodic_timer(1,refresh)
    end
    mp.observe_property('osd-dimensions','native',function()
        if not visible then return end
        if resize_timer then resize_timer:kill() end
        resize_timer=mp.add_timeout(0.06,function() resize_timer=nil;draw() end)
    end)
    return {toggle=toggle,close=close,is_open=function() return visible end}
end
return M
