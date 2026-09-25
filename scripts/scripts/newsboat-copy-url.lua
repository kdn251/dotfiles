-- Keep the original website URL even after playback switches to a local file.
local original = os.getenv('NEWSBOAT_MEDIA_URL')
local helper = os.getenv('HOME') .. '/scripts/newsboat-copy-url.py'
local copying = false
mp.add_forced_key_binding('Ctrl+c', 'newsboat-copy-url', function()
    if copying then return end
    local url = original or mp.get_property('path', '')
    if not url:match('^https?://') then
        mp.osd_message('No video URL available to copy', 2)
        return
    end
    copying = true
    mp.command_native_async({name='subprocess', playback_only=false,
        args={'python3', helper, url}}, function(success, result)
        copying = false
        if success and result and result.status == 0 then
            mp.osd_message('Video URL copied', 2)
        else
            mp.osd_message('Could not copy video URL', 2)
        end
    end)
end)
