local utils=require 'mp.utils'
local helper=os.getenv('HOME')..'/scripts/newsboat-player-info.py'
local pending=false
local chapter_generation=0
local playing=false
local deferred
local function url()
    return mp.get_property_native('user-data/newsboat/url','')~='' and
        mp.get_property_native('user-data/newsboat/url') or os.getenv('NEWSBOAT_MEDIA_URL') or ''
end
local function refresh_status()
    local current,path=url(),mp.get_property('path','')
    if not playing or current=='' or path=='' or pending then return end
    pending=true
    mp.command_native_async({name='subprocess',playback_only=false,capture_stdout=true,capture_stderr=true,
        args={'python3',helper,'status',current,path}},function(ok,result)
        pending=false
        if current~=url() or path~=mp.get_property('path','') then return end
        if ok and result and result.status==0 then
            mp.set_property_native('user-data/newsboat/playback-status',result.stdout:gsub('%s+$',''))
        end
    end)
end
local function load_chapters()
    chapter_generation=chapter_generation+1
    local version=chapter_generation
    local current=url()
    if current=='' or mp.get_property_number('chapters',0)>0 then return end
    -- The normal YouTube resolver already fetched chapters (including a known
    -- empty list). Do not repeat extraction just because there are zero chapters.
    local result=mp.get_property_native('user-data/mpv/ytdl/json-subprocess-result')
    local data=result and result.status==0 and type(result.stdout)=='string' and utils.parse_json(result.stdout)
    local id=current:match('[?&]v=([%w_-]+)') or current:match('youtu%.be/([%w_-]+)') or
        current:match('/shorts/([%w_-]+)') or current:match('/live/([%w_-]+)')
    if type(data)=='table' and id and data.id==id then
        local chapters={}
        for _,chapter in ipairs(type(data.chapters)=='table' and data.chapters or {}) do
            if type(chapter.start_time)=='number' and chapter.start_time>=0 then
                chapters[#chapters+1]={time=chapter.start_time,title=chapter.title or 'Chapter'}
            end
        end
        if #chapters>0 then mp.set_property_native('chapter-list',chapters) end
        return
    end
    mp.command_native_async({name='subprocess',playback_only=false,capture_stdout=true,capture_stderr=true,
        args={'python3',helper,'chapters',current}},function(ok,result)
        if version~=chapter_generation or current~=url() or mp.get_property_number('chapters',0)>0 then return end
        if ok and result and result.status==0 then
            local chapters=utils.parse_json(result.stdout)
            if type(chapters)=='table' and #chapters>0 then mp.set_property_native('chapter-list',chapters) end
        end
    end)
end
mp.add_periodic_timer(2,refresh_status)
mp.register_event('start-file',function()
    playing=false
    chapter_generation=chapter_generation+1
    if deferred then deferred:kill();deferred=nil end
end)
mp.register_event('playback-restart',function()
    if playing then return end
    playing=true
    deferred=mp.add_timeout(.1,function()
        deferred=nil
        refresh_status();load_chapters()
    end)
end)
mp.observe_property('user-data/newsboat/url','native',function()
    chapter_generation=chapter_generation+1
    mp.set_property_native('user-data/newsboat/playback-status','')
end)
