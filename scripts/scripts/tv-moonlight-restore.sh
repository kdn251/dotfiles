#!/usr/bin/env bash
# Restore the Samsung TV's display, audio, controller, and Moonlight window.
# Safe to run over SSH while a game is streaming; it does not restart Moonlight.
set -euo pipefail

export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
if [[ -z ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
  HYPRLAND_INSTANCE_SIGNATURE=$(hyprctl instances -j | jq -r '.[0].instance // empty')
  export HYPRLAND_INSTANCE_SIGNATURE
fi
if [[ -z ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
  echo 'No Hyprland session found for this user.' >&2
  exit 1
fi

tv_description='Samsung Electric Company QN90D 0x01000E00'
tv_sink='alsa_output.pci-0000_c1_00.1.hdmi-stereo'
tv_monitor=$(hyprctl -j monitors | jq -r --arg desc "$tv_description" '
  .[] | select(.description == $desc) | .name
' | head -n 1)
if [[ -z $tv_monitor ]]; then
  echo 'Samsung QN90D is not connected; leaving the laptop setup alone.' >&2
  exit 1
fi

if ! hyprctl -j monitors | jq -e --arg name "$tv_monitor" '
  any(.[]; .name == $name and .width == 3840 and .height == 2160 and .refreshRate >= 59.9)
' >/dev/null; then
  hyprctl keyword monitor "desc:$tv_description,3840x2160@60,0x0,2.4" >/dev/null
fi
if ! hyprctl -j workspaces | jq -e --arg name "$tv_monitor" '
  any(.[]; .id == 7 and .monitor == $name)
' >/dev/null; then
  hyprctl dispatch moveworkspacetomonitor "7 $tv_monitor" >/dev/null
fi

if pactl list short sinks | awk -v name="$tv_sink" '$2 == name { found = 1 } END { exit !found }'; then
  pactl set-default-sink "$tv_sink"
  sink_index=$(pactl -f json list sinks | jq -r --arg name "$tv_sink" '.[] | select(.name == $name) | .index')
  while IFS= read -r stream_index; do
    [[ -n $stream_index ]] && pactl move-sink-input "$stream_index" "$tv_sink"
  done < <(pactl -f json list sink-inputs | jq -r --argjson sink "$sink_index" '
    .[] | select(.properties["application.id"] == "com.moonlight_stream.Moonlight")
    | select(.sink != $sink) | .index
  ')
else
  echo 'TV audio output is unavailable.' >&2
fi

controller_address=$(bluetoothctl devices Paired 2>/dev/null | awk '$0 ~ /8BitDo Ultimate 2 Wireless$/ { print $2; exit }')
if [[ -n $controller_address ]] && ! bluetoothctl info "$controller_address" | grep -q 'Connected: yes'; then
  bluetoothctl connect "$controller_address" >/dev/null 2>&1 || true
fi

moonlight_pid=$(pgrep -xo moonlight || true)
if [[ -z $moonlight_pid ]]; then
  hyprctl dispatch focusmonitor "$tv_monitor" >/dev/null
  hyprctl dispatch workspace 7 >/dev/null
  hyprctl dispatch exec '/home/knaught/scripts/moonlight-launch.sh' >/dev/null
  for _ in {1..20}; do
    moonlight_pid=$(pgrep -xo moonlight || true)
    [[ -n $moonlight_pid ]] && break
    sleep 0.5
  done
elif ! pgrep -f '^bash /home/knaught/scripts/moonlight-launch.sh' >/dev/null; then
  hyprctl dispatch exec "/home/knaught/scripts/moonlight-launch.sh --attach $moonlight_pid" >/dev/null
fi

if [[ -z $moonlight_pid ]]; then
  echo 'Moonlight did not start.' >&2
  exit 1
fi

window_address=
for _ in {1..20}; do
  window_address=$(hyprctl -j clients | jq -r --argjson pid "$moonlight_pid" '
    .[] | select(.class == "com.moonlight_stream.Moonlight" and .pid == $pid)
    | .address
  ' | head -n 1)
  [[ -n $window_address ]] && break
  sleep 0.5
done
if [[ -z $window_address ]]; then
  echo 'Moonlight is running, but its window is not visible yet.' >&2
  exit 1
fi

hyprctl dispatch movetoworkspacesilent "7,address:$window_address" >/dev/null
hyprctl dispatch focusmonitor "$tv_monitor" >/dev/null
hyprctl dispatch workspace 7 >/dev/null
hyprctl dispatch focuswindow "address:$window_address" >/dev/null

hyprctl -j monitors | jq -r --arg name "$tv_monitor" '
  .[] | select(.name == $name) | "TV: \(.width)x\(.height) @ \(.refreshRate) Hz; workspace \(.activeWorkspace.id)"
'
printf 'Audio: %s\n' "$(pactl get-default-sink)"
if [[ -n $controller_address ]]; then
  bluetoothctl info "$controller_address" | awk -F': ' '/Connected:/ { print "Controller connected: " $2 }'
else
  echo 'Controller: 8BitDo Ultimate 2 Wireless is not paired.'
fi
echo 'Moonlight: focused on TV workspace 7.'
echo 'TV Game Mode is controlled by the TV; check its Game Bar if input still feels delayed.'
