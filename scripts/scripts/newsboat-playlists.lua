-- Shift+P opens the playing creator's playlists in the originating Newsboat.
local pending = false
mp.add_key_binding('P', 'newsboat-playlists', function()
    if pending then return end
    local url = mp.get_property_native('user-data/newsboat/url', '')
    if url == '' then url = os.getenv('NEWSBOAT_MEDIA_URL') or mp.get_property('path', '') end
    pending = true
    mp.command_native_async({name='subprocess', playback_only=false,
        args={'python3', os.getenv('HOME')..'/scripts/newsboat-playlists.py', 'request', url}},
        function(success, result)
            pending = false
            mp.osd_message(success and result and result.status == 0
                and 'Opening playlists in Newsboat' or 'Could not open playlists — restart Newsboat and reopen this video', 3)
        end)
end)
