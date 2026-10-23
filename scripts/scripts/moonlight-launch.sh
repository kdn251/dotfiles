#!/usr/bin/env bash
# Give Moonlight a readable TV menu and send its audio to the TV when docked.
set -u

tv_sink=alsa_output.pci-0000_c1_00.1.hdmi-stereo
tv_connected=false

if hyprctl -j monitors 2>/dev/null | jq -e '
  any(.[]; .description | startswith("Samsung Electric Company QN90D"))
' >/dev/null 2>&1; then
  tv_connected=true
  tv_monitor=$(hyprctl -j monitors | jq -r '.[] | select(.description | startswith("Samsung Electric Company QN90D")) | .name' | head -n 1)
  # This affects Moonlight's Qt menu; the streamed game uses its own renderer.
  export QT_SCALE_FACTOR=0.65
fi

if "$tv_connected" && pactl list short sinks 2>/dev/null | awk -v name="$tv_sink" '$2 == name { found = 1 } END { exit !found }'; then
  # Persist the TV output for other applications too, as in the working setup.
  pactl set-default-sink "$tv_sink"
else
  tv_connected=false
fi

if [[ ${1-} == --attach && ${2-} =~ ^[0-9]+$ ]]; then
  # Reattach the watcher after an output mode change without restarting a game.
  moonlight_pid=$2
  attached=true
else
  /usr/bin/moonlight "$@" &
  moonlight_pid=$!
  attached=false
fi

# Moonlight creates a new audio stream when a game starts. Route each stream
# while this instance is open, including when WirePlumber restores an old sink.
while kill -0 "$moonlight_pid" 2>/dev/null; do
  if "$tv_connected"; then
    # Qt can remap its menu onto the laptop when a stream window closes.
    while IFS= read -r window_address; do
      [[ -z "$window_address" ]] && continue
      hyprctl dispatch movetoworkspacesilent "7,address:$window_address" >/dev/null
      hyprctl dispatch focusmonitor "$tv_monitor" >/dev/null
      hyprctl dispatch focuswindow "address:$window_address" >/dev/null
    done < <(hyprctl -j clients 2>/dev/null | jq -r '
      .[] | select(.class == "com.moonlight_stream.Moonlight")
      | select(.workspace.id != 7) | .address
    ' 2>/dev/null)

    # PipeWire can replace a sink and give it a new ID after a display modeset.
    tv_sink_index=$(pactl -f json list sinks 2>/dev/null | jq -r --arg name "$tv_sink" '.[] | select(.name == $name) | .index' 2>/dev/null)
  else
    tv_sink_index=
  fi
  if [[ -n "$tv_sink_index" ]]; then
    while IFS= read -r stream_index; do
      [[ -n "$stream_index" ]] && pactl move-sink-input "$stream_index" "$tv_sink" 2>/dev/null || true
    done < <(pactl -f json list sink-inputs 2>/dev/null | jq -r --argjson sink "$tv_sink_index" '
      .[] | select(.properties["application.id"] == "com.moonlight_stream.Moonlight")
      | select(.sink != $sink) | .index
    ' 2>/dev/null)
  fi
  sleep 2
done

if ! "$attached"; then
  wait "$moonlight_pid"
fi
