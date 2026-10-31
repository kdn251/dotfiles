-- Preview accepts a click but otherwise stays muted until explicitly promoted.
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
    mp.set_property_native('user-data/preview-ready',true)
    mp.osd_message('',0)
end)
mp.osd_message('Loading muted preview…',60)
