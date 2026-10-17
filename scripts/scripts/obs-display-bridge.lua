local obs = obslua
local ffi = require("ffi")
ffi.cdef[[void knaught_queue_display_create(const char *json);]]
local bridge = ffi.load("/home/knaught/scripts/obs-display-create.so")
local request_path = "/home/knaught/.local/state/obs-display-follow/request.json"

local function poll()
    local file = io.open(request_path, "r")
    if not file then return end
    local json = file:read("*a")
    file:close()
    os.remove(request_path)
    bridge.knaught_queue_display_create(json)
end

function script_description()
    return "Creates automatic display captures on OBS's UI thread so PipeWire portal replies are processed correctly."
end

function script_load(settings)
    obs.timer_add(poll, 500)
end

function script_unload()
    obs.timer_remove(poll)
end
