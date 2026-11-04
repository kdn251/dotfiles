-- Keep MPV's normal screenshot naming, location and format, then copy it.
mp.add_key_binding(nil,'save-and-copy',function()
    mp.command_native_async({'screenshot','video'},function(ok,result)
        if not ok or type(result)~='table' or not result.filename then
            mp.osd_message('Screenshot could not be saved',3)
            return
        end
        mp.command_native_async({name='subprocess',playback_only=false,
            args={'python3',os.getenv('HOME')..'/scripts/mpv-copy-screenshot.py',result.filename},
            capture_stdout=true,capture_stderr=true},function(copied,response)
            if copied and response and response.status==0 then
                mp.osd_message('Screenshot saved and copied',2)
            else
                mp.osd_message('Screenshot saved; clipboard copy failed',3)
            end
        end)
    end)
end)
