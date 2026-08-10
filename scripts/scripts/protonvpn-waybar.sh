#!/bin/bash

# Proton VPN waybar module.
#   (no args) -> JSON status for waybar (connected = proton0 interface up)
#   toggle    -> show/hide the Proton VPN app window like a menubar dropdown
#                (launches the app if it isn't running)

APP_CLASS_RE='^(proton\.vpn\.app\.gtk|protonvpn-app)$'
SPECIAL_WS="special:protonvpn"
MARGIN_RIGHT=10
MARGIN_TOP=5

get_window() {
  hyprctl clients -j | jq -c --arg re "$APP_CLASS_RE" 'first(.[] | select(.class | test($re))) // empty'
}

# Anchor the window below the bar at the top-right of the focused monitor,
# like a macOS menubar dropdown. Runs a second pass because the reported
# window width changes once the window is mapped on a real workspace.
position_window() {
  position_window_once "$1"
  sleep 0.2
  position_window_once "$1"
}

position_window_once() {
  local ADDR="$1"
  local MON WIN
  MON=$(hyprctl monitors -j | jq -c '.[] | select(.focused)')
  WIN=$(get_window)

  local MX MY MW SCALE RES_TOP WINW X Y
  MX=$(echo "$MON" | jq -r '.x')
  MY=$(echo "$MON" | jq -r '.y')
  MW=$(echo "$MON" | jq -r '.width')
  SCALE=$(echo "$MON" | jq -r '.scale')
  RES_TOP=$(echo "$MON" | jq -r '.reserved[1]')
  WINW=$(echo "$WIN" | jq -r '.size[0]')

  X=$(awk -v mx="$MX" -v mw="$MW" -v s="$SCALE" -v w="$WINW" -v m="$MARGIN_RIGHT" \
    'BEGIN{printf "%d", mx + mw/s - w - m}')
  Y=$(awk -v my="$MY" -v r="$RES_TOP" -v m="$MARGIN_TOP" \
    'BEGIN{printf "%d", my + r + m}')

  hyprctl dispatch movewindowpixel "exact $X $Y,address:$ADDR" >/dev/null
}

toggle_window() {
  WIN_JSON=$(get_window)

  if [ -z "$WIN_JSON" ]; then
    setsid protonvpn-app >/dev/null 2>&1 &
    # Wait for the window to appear, then anchor it top-right
    for _ in $(seq 1 20); do
      sleep 0.5
      WIN_JSON=$(get_window)
      [ -n "$WIN_JSON" ] && break
    done
    [ -z "$WIN_JSON" ] && exit 0
    position_window "$(echo "$WIN_JSON" | jq -r '.address')"
    exit 0
  fi

  ADDR=$(echo "$WIN_JSON" | jq -r '.address')
  WS=$(echo "$WIN_JSON" | jq -r '.workspace.name')

  if [ "$WS" == "$SPECIAL_WS" ]; then
    ACTIVE_WS=$(hyprctl activeworkspace -j | jq -r '.id')
    # Silent move: reveal the window without focusing it, so the cursor
    # doesn't warp over to it.
    hyprctl dispatch movetoworkspacesilent "$ACTIVE_WS,address:$ADDR" >/dev/null
    position_window "$ADDR"
  else
    hyprctl dispatch movetoworkspacesilent "$SPECIAL_WS,address:$ADDR" >/dev/null
  fi
}

# --- EXECUTION ---
if [ "$1" == "toggle" ]; then
  toggle_window
  exit 0
fi

# --- WAYBAR OUTPUT ---
if ip link show proton0 &>/dev/null; then
  # Server name from the active NM connection on proton0 (best effort)
  SERVER=$(nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null | awk -F: '$2=="proton0"{print $1; exit}')
  echo "{\"text\": \"󰦝\", \"class\": \"connected\", \"tooltip\": \"Proton VPN: connected${SERVER:+ ($SERVER)}\"}"
else
  echo "{\"text\": \"󰦝\", \"class\": \"disconnected\", \"tooltip\": \"Proton VPN: disconnected\"}"
fi
