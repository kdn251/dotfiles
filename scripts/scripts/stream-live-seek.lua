-- Live HLS timestamps need not start at zero. Seek within the actual buffered
-- range, never duration-based percentages or a position beyond available data.
local function active()
    local service=mp.get_property_native('user-data/stream-service','')
    return service=='Twitch' or service=='Kick' or service=='YouTube' or service=='Rumble'
end
local function bounds()
    local cache=mp.get_property_native('demuxer-cache-state',{}) or {}
    local first,last
    for _,range in ipairs(cache['seekable-ranges'] or {}) do
        if range.start and range['end'] then
            first=math.min(first or range.start,range.start)
            last=math.max(last or range['end'],range['end'])
        end
    end
    return first,last
end
local function seek(value,flags)
    value=tonumber(value)
    if not value or not active() then return end
    flags=flags or 'relative'
    local first,last=bounds()
    local position=mp.get_property_number('time-pos')
    if not first or not last or not position then return end
    local target
    if flags:find('absolute%-percent') then target=first+(last-first)*value/100
    elseif flags:find('absolute') then target=value
    else target=position+value end
    local edge=math.max(first,last-.05)
    if target>=edge and position>=edge-.15 then
        -- Already caught up: let the demuxer wait for the next live segment.
        mp.set_property_native('pause',false)
        return
    end
    target=math.max(first,math.min(edge,target))
    mp.commandv('seek',target,'absolute+exact')
end
mp.register_script_message('stream-safe-seek',seek)
local keys={l=5,h=-5,j=-60,k=60,RIGHT=5,LEFT=-5,UP=60,DOWN=-60}
local function bindings()
    for key,value in pairs(keys) do
        local name='stream-safe-seek-'..key
        mp.remove_key_binding(name)
        if active() then mp.add_forced_key_binding(key,name,function() seek(value,'relative') end,{repeatable=true}) end
    end
    mp.remove_key_binding('stream-safe-live')
    if active() then mp.add_forced_key_binding('G','stream-safe-live',function() seek(100,'absolute-percent') end) end
end
mp.observe_property('user-data/stream-service','native',bindings)
