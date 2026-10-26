#!/bin/bash
# LocalSend as a reusable, top-right Waybar dropdown.
set -u
SPECIAL_WS="special:localsend"
get_window() {
  hyprctl clients -j | jq -c 'first(.[] | select(.class == "org.localsend.localsend_app" and .title == "LocalSend")) // empty'
}
hide_window() {
  hyprctl dispatch movetoworkspacesilent "$SPECIAL_WS,address:$1" >/dev/null
}
position_window() {
  local addr="$1" geometry
  geometry=$(hyprctl monitors -j | python3 -c '
import json,sys
m=next(m for m in json.load(sys.stdin) if m["focused"])
w,h=m["width"],m["height"]
if m.get("transform",0) % 2: w,h=h,w
w,h=int(w/m["scale"]),int(h/m["scale"])
left,top,right,bottom=m["reserved"]
pw,ph=min(480,w-left-right-20),min(700,h-top-bottom-20)
print(pw,ph,m["x"]+w-right-pw-10,m["y"]+top+5)')
  local width height x y
  read -r width height x y <<< "$geometry"
  hyprctl dispatch setfloating "address:$addr" >/dev/null
  hyprctl dispatch resizewindowpixel "exact $width $height,address:$addr" >/dev/null
  hyprctl dispatch movewindowpixel "exact $x $y,address:$addr" >/dev/null
}
case "${1:-toggle}" in
  hide-if-visible)
    win=$(get_window)
    [ -z "$win" ] && exit 0
    [ "$(jq -r '.workspace.name' <<< "$win")" = "$SPECIAL_WS" ] && exit 0
    hide_window "$(jq -r '.address' <<< "$win")"
    ;;
  toggle)
    exec 9>"${XDG_RUNTIME_DIR:-/tmp}/localsend-waybar.lock"
    flock -n 9 || exit 0
    win=$(get_window)
    if [ -n "$win" ] && [ "$(jq -r '.workspace.name' <<< "$win")" != "$SPECIAL_WS" ]; then
      hide_window "$(jq -r '.address' <<< "$win")"
      exit 0
    fi
    "$HOME/scripts/panel-guard.sh" close-others localsend
    if [ -z "$win" ]; then
      setsid env GTK_CSD=1 localsend 9>&- >"${XDG_RUNTIME_DIR:-/tmp}/localsend-waybar.log" 2>&1 < /dev/null &
      for ((i=0;i<40;i++)); do
        sleep 0.25
        win=$(get_window)
        [ -n "$win" ] && break
      done
      if [ -z "$win" ]; then
        notify-send 'LocalSend' 'Could not open LocalSend. Please try again.'
        exit 1
      fi
    fi
    addr=$(jq -r '.address' <<< "$win")
    workspace=$(hyprctl activeworkspace -j | jq -r '.id')
    hyprctl dispatch movetoworkspacesilent "$workspace,address:$addr" >/dev/null
    position_window "$addr"
    sleep 0.2
    position_window "$addr"
    hyprctl dispatch focuswindow "address:$addr" >/dev/null
    ;;
esac
