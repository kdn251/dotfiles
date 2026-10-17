-- This script is loaded only by the Space-bar preview.
local mp = require 'mp'
local utils = require 'mp.utils'
local binding = os.getenv('THUNAR_PREVIEW_SELECTION')
local helper = os.getenv('THUNAR_PREVIEW_HELPER')

mp.register_event('file-loaded', function()
    local path = mp.get_property('path')
    if not path then return end
    local state = io.open('/tmp/thunar-preview-file', 'w')
    if state then state:write(path); state:close() end
    if not binding or binding == '' or not helper then return end
    -- Serialize updates so rapid navigation cannot leave an older file selected.
    local result = utils.subprocess({args = {'python3', helper, '--select', binding, path},
                                    cancellable = false})
    if result.status ~= 0 then
        mp.msg.warn('Could not synchronize Thunar selection: ' .. (result.stderr or ''))
    end
end)
