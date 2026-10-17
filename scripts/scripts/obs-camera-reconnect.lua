-- Follow this Cam Link across Linux device-number changes and late USB arrival.
local obs = obslua
local ffi = require("ffi")
ffi.cdef[[char *realpath(const char *path, char *resolved_path);]]

local DEVICE = "/dev/v4l/by-id/usb-Elgato_Cam_Link_4K_A29YB53135TO7F-video-index0"
local SOURCE_UUID = "d2add3c9-9810-4a7b-9040-a95da43468af"
local buffer = ffi.new("char[4096]")

local function check_camera()
    -- Retain the permanent path while absent; switching back to the actual
    -- node when it arrives forces V4L2 to reopen it. Using the actual node
    -- while connected also preserves OBS's native udev reconnect handling.
    local resolved = ffi.C.realpath(DEVICE, buffer)
    local device = resolved ~= nil and ffi.string(buffer) or DEVICE
    local source = obs.obs_get_source_by_uuid(SOURCE_UUID)
    if source == nil then return end
    if obs.obs_source_get_unversioned_id(source) == "v4l2_input" then
        local settings = obs.obs_source_get_settings(source)
        if obs.obs_data_get_string(settings, "device_id") ~= device then
            obs.obs_data_set_string(settings, "device_id", device)
            obs.obs_source_update(source, settings)
            obs.script_log(obs.LOG_INFO, "Cam Link reconnect: " .. device)
        end
        obs.obs_data_release(settings)
    end
    obs.obs_source_release(source)
end

function script_description()
    return "Reconnects Kevin's Sony camera through its Cam Link when USB appears or changes device number. Checks every two seconds without restarting a connected feed."
end

function script_load(settings)
    obs.timer_add(check_camera, 2000)
end

function script_unload()
    obs.timer_remove(check_camera)
end
