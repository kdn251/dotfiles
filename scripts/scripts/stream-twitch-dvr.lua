-- Optional server-side Twitch rewind. Discovery never delays live playback.
local utils=require 'mp.utils'
local root=(os.getenv('HOME') or '')..'/scripts/'
local dvr={}
local data, job, generation, channel, mode, loading=nil,nil,0,'','live',false
local loaded_duration=0
local function is_twitch()
    return mp.get_property_native('user-data/stream-service','')=='Twitch'
end
local function publish()
    if not data then mp.set_property_native('user-data/stream-dvr',{});return end
    local position=mp.get_property_number('time-pos',0)
    if mode=='live' then
        local cache=mp.get_property_native('demuxer-cache-state',{}) or {}
        local edge=position
        for _,r in ipairs(cache['seekable-ranges'] or {}) do edge=math.max(edge,r['end'] or edge) end
        position=math.max(0,os.time()-data.started_at-math.max(0,edge-position))
    end
    mp.set_property_native('user-data/stream-dvr',{available=true,mode=mode,
        duration=data.duration,position=math.min(position,data.duration),loading=loading})
end
local function request(args,callback)
    local version=generation
    job=mp.command_native_async({name='subprocess',playback_only=false,args=args,
        capture_stdout=true,capture_stderr=true},function(ok,result)
        if version~=generation then return end
        job=nil
        callback(ok and result and result.status==0 and utils.parse_json(result.stdout or '') or nil)
    end)
end
local function discover()
    if not is_twitch() or channel=='' or job or loading then return end
    request({'python3',root..'twitch-dvr.py',channel},function(result)
        if result and result.path and result.started_at and result.duration then data=result;publish() end
    end)
end
function dvr.live()
    if not data then return false end
    if mode=='live' and not loading then return false end
    if job then mp.abort_async_command(job);job=nil end
    loading=true;publish();mp.osd_message('Returning to live…',2)
    request({'python3',root..'twitch-stream-url.py',channel,'--playback'},function(result)
        if not result or not result.best then loading=false;publish();mp.osd_message('Could not return to live. Try again.',3);return end
        mode='live';publish()
        mp.command_native({'loadfile',result.best,'replace',0,{['rebase-start-time']='no',pause='no'}})
    end)
    return true
end
function dvr.seek(value,flags)
    if not data or not is_twitch() then return false end
    if flags:find('absolute%-percent') and value>=99.99 then return dvr.live() end
    if mode=='live' and not flags:find('absolute') then
        local cache=mp.get_property_native('demuxer-cache-state',{}) or {}
        local pos=mp.get_property_number('time-pos',0)
        for _,r in ipairs(cache['seekable-ranges'] or {}) do
            if pos+value>=r.start and pos+value<=r['end'] then return false end
        end
    end
    local status=mp.get_property_native('user-data/stream-dvr',{}) or {}
    local target
    if flags:find('absolute%-percent') then target=data.duration*value/100
    elseif flags:find('absolute') then target=value
    else target=(status.position or 0)+value end
    if target>=data.duration-2 then return dvr.live() end
    if loading then return true end
    target=math.max(0,math.min(data.duration-.1,target))
    if mode=='rewind' and target<loaded_duration-2 then mp.commandv('seek',target,'absolute+exact');return true end
    loaded_duration=data.duration
    mode='rewind';loading=true;publish();mp.osd_message('Loading earlier broadcast…',2)
    mp.command_native({'loadfile',data.path,'replace',0,{start=tostring(target),
        ['rebase-start-time']='yes',demuxer='lavf',['demuxer-lavf-format']='hls',
        ['demuxer-lavf-o']='protocol_whitelist=%35%file,http,https,tcp,tls,crypto,data',pause='no'}})
    return true
end
local function reset()
    generation=generation+1
    if job then mp.abort_async_command(job);job=nil end
    data=nil;mode='live';loading=false
    channel=mp.get_property_native('user-data/stream-name','')
    publish()
    local version=generation
    mp.add_timeout(2,function()if version==generation then discover() end end)
end
mp.observe_property('user-data/stream-name','native',reset)
mp.observe_property('user-data/stream-service','native',reset)
mp.register_event('playback-restart',function()loading=false;publish()end)
mp.register_event('end-file',function(event)
    if mode=='rewind' and (event.reason=='eof' or event.reason=='error') then
        mp.add_timeout(0,function()dvr.live()end)
    end
end)
mp.add_periodic_timer(1,publish)
mp.add_periodic_timer(60,discover)
mp.register_event('shutdown',function()if job then mp.abort_async_command(job) end end)
return dvr
