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
    local copied, reordering, feedback = nil, false, nil
    local pending_y = nil
    local read_serial = 0
    local thumbnails, image_jobs, image_count, generation = {}, {}, 0, 0
    local draw
    local viewport_start = 1
    -- 42 belongs to thumbfast; keep Queue slots away from seek/Up Next overlays.
    local image_base = 50
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
        local function box(l,t,r,b,color,alpha,radius)
            a:new_event();a:append('{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H'..color..'&\\1a&H'..(alpha or '00')..'&}')
            a:draw_start()
            if radius then
                a:append('{\\p1}')
                local d=radius;local c=d*.55228475
                a:append(string.format('m %f %f l %f %f b %f %f %f %f %f %f l %f %f b %f %f %f %f %f %f l %f %f b %f %f %f %f %f %f l %f %f b %f %f %f %f %f %f',
                    l+d,t,r-d,t,r-d+c,t,r,t+d-c,r,t+d,
                    r,b-d,r,b-d+c,r-d+c,b,r-d,b,
                    l+d,b,l+d-c,b,l,b-d+c,l,b-d,
                    l,t+d,l,t+d-c,l+d-c,t,l+d,t))
            else a:rect_cw(l,t,r,b) end
            a:draw_stop()
        end
        local function text(px,py,size,color,value)
            a:new_event();a:append(string.format('{\\an7\\pos(%f,%f)\\fnSans\\fs%d\\bord0\\shad0\\1c&H%s&}',px,py,size,color))
            a:append(value)
        end
        box(0,0,width,720,'000000','88')
        box(x-1,top-1,x+panel+1,top+height+1,'807060',nil,15)
        box(x,top,x+panel,top+height,'2E1E1E',nil,14)
        text(x+22,top+14,26,'F4D6CD','Queue')
        text(x+panel-145,top+20,16,'C2ADA6',#rows..' videos')
        -- Keep rows stationary until selection crosses an edge of the viewport.
        viewport_start=math.max(1,math.min(viewport_start,math.max(1,#rows-shown+1)))
        if selected<viewport_start then viewport_start=selected end
        if selected>=viewport_start+shown then viewport_start=selected-shown+1 end
        local start=viewport_start
        local limit = math.max(8,math.floor((panel-245)/12))
        local needed = {}
        if #rows == 0 then text(x+22,top+65,21,'C2ADA6',message) end
        for i=start,math.min(#rows,start+shown-1) do
            local row = rows[i]
            local y = top+54+(i-start)*66
            local playing = row.url == current()
            if playing then box(x+10,y,x+panel-10,y+61,'45362B',nil,8) end
            if i==selected then box(x+10,y,x+panel-10,y+61,'655032',nil,8) end
            if playing then box(x+13,y+8,x+17,y+53,'DEC294',nil,2) end
            local image = thumbnails[row.url]
            if image then
                local scale=h/720
                local id = image_base+i-start
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
            local pct = row.percent or 0
            if playing then pct = math.floor(mp.get_property_number('percent-pos',pct)) end
            text(x+132,y+6,20,playing and 'DEC294' or 'F4D6CD',
                (playing and '▶ ' or '')..i..'. '..clean(row.title or row.url,limit))
            text(x+132,y+34,16,playing and 'DEC294' or 'C2ADA6',
                (playing and 'NOW PLAYING  ·  ' or '')..clean(row.source or '',playing and math.max(8,limit-15) or limit)..'  ·  '..pct..'% watched')
        end
        -- Warm nearby rows after visible requests so scrolling doesn't start
        -- thumbnail downloads only once a row is already on screen.
        for distance=1,4 do
            local after=rows[start+shown-1+distance]
            local before=rows[start-distance]
            if after then request_image(after.url) end
            if before then request_image(before.url) end
        end
        text(x+22,top+height-27,15,'C2ADA6',feedback or 'j/k Browse   yy Pick up   p Below   P Above   Enter Play   Esc Close')
        for id in pairs(displayed) do
            if not needed[id] then mp.commandv('overlay-remove',id) end
        end
        displayed=needed
        overlay.res_x,overlay.res_y,overlay.data = width,720,a.text
        overlay:update()
    end
    local function refresh(preferred)
        if job or not visible or reordering then return end
        read_serial=read_serial+1
        local serial,epoch=read_serial,generation
        job = mp.command_native_async({name='subprocess',playback_only=false,capture_stdout=true,
            args={'python3',directory..'newsboat_queue.py','menu-json'}},function(ok,result)
            if serial~=read_serial or epoch~=generation then return end
            job=nil
            if not visible then return end
            local updated = ok and result and result.status==0 and utils.parse_json(result.stdout)
            if updated then
                local wanted = preferred or (rows[selected] and rows[selected].queue_token)
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
    local function paste(before)
        pending_y=nil
        if reordering then return end
        local target=rows[selected]
        if not copied then feedback='Press yy to pick up a row first';draw();return end
        if not target then return end
        if copied.queue_token==target.queue_token then feedback='That row is already here';draw();return end
        local source
        for _,row in ipairs(rows) do if row.queue_token==copied.queue_token then source=row end end
        if not source then feedback='Picked-up video is no longer in Queue';copied=nil;draw();return end
        reordering=true;feedback='Moving queue row…'
        read_serial=read_serial+1
        if job then mp.abort_async_command(job);job=nil end
        local epoch,token=generation,source.queue_token
        mp.command_native_async({name='subprocess',playback_only=false,capture_stdout=true,capture_stderr=true,
            args={'python3',directory..'newsboat_queue.py',before and 'move-before' or 'move-after',source.url,target.url}},function(ok,result)
            reordering=false
            if not visible then return end
            if epoch~=generation then refresh();return end
            if ok and result and result.status==0 then
                feedback=nil;refresh(token)
            else feedback='Could not move row; the queue may have changed';refresh() end
            draw()
        end)
        draw()
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
    local function move(delta) pending_y=nil;selected=math.max(1,math.min(#rows,selected+delta));draw() end
    local function toggle()
        if visible then close();return end
        visible=true;rows={};selected=1;viewport_start=1;message='Loading queue…';copied=nil;feedback=nil;pending_y=nil
        for url,image in pairs(thumbnails) do if image==false then thumbnails[url]=nil end end
        if opened then opened() end
        bind('j','down',function() move(1) end,true)
        bind('k','up',function() move(-1) end,true)
        bind('DOWN','arrow-down',function() move(1) end,true)
        bind('UP','arrow-up',function() move(-1) end,true)
        -- Handle the two presses ourselves: a forced single-y binding can
        -- consume the first key before mpv resolves a y-y sequence.
        bind('y','yank',function()
            local row=rows[selected]
            if not row then return end
            if pending_y==row.queue_token then
                copied=row;pending_y=nil
                feedback='Picked up: '..clean(row.title or row.url,65)..'  ·  p below / P above'
            else
                pending_y=row.queue_token
                feedback='Press y again to pick up this row'
            end
            draw()
        end)
        bind('p','paste-after',function() paste(false) end)
        bind('P','paste-before',function() paste(true) end)
        bind('W','toggle',close)
        bind('ESC','close',close)
        bind('q','dismiss',close)
        bind('ENTER','play',function()
            local row=rows[selected]
            if not row then return end
            close(row.url~=current())
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
