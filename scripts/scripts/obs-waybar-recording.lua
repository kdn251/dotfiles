local obs = obslua

local STATUS_FILE = "/tmp/recording.txt"
local WAYBAR_SIGNAL = "pkill -RTMIN+8 waybar"

local function write_status(text)
  local f = io.open(STATUS_FILE, "w")
  if f then
    f:write(text)
    f:close()
  end
  os.execute(WAYBAR_SIGNAL .. " >/dev/null 2>&1")
end

local function on_event(event)
  if event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTED then
    write_status("●\n")
  elseif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED then
    write_status("")
  end
end

function script_description()
  return "Writes OBS recording state to /tmp/recording.txt and signals waybar."
end

function script_load(_)
  obs.obs_frontend_add_event_callback(on_event)
  if obs.obs_frontend_recording_active() then
    write_status("●\n")
  end
end

function script_unload()
  if obs.obs_frontend_recording_active() == false then
    write_status("")
  end
end
