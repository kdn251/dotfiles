-- Use the same pin-preserving fullscreen toggle as Mod+F under Hyprland.
local utils = require 'mp.utils'
mp.add_key_binding('f', 'pip-fullscreen', function()
    if not os.getenv('HYPRLAND_INSTANCE_SIGNATURE') then
        mp.commandv('cycle', 'fullscreen')
        return
    end
    mp.command_native_async({
        name = 'subprocess', playback_only = false,
        args = {os.getenv('HOME') .. '/scripts/toggle-pip-fullscreen.sh',
                '--pid', tostring(utils.getpid())},
    }, function(success, result, error)
        if not success or result.status ~= 0 then
            mp.msg.error('Fullscreen toggle failed: ' .. tostring(error))
        end
    end)
end)
