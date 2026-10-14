#!/bin/bash
# One Mod+F handler for normal windows and pinned browser miniplayers.
set -euo pipefail
runtime="${XDG_RUNTIME_DIR:-/tmp}"
exec 9>"$runtime/pip-fullscreen-$UID.lock"
flock -n 9 || exit 0
focused=$(hyprctl activewindow -j)
address=$(jq -r '.address // empty' <<<"$focused")
[ -n "$address" ] || exit 0
title=$(jq -r '.title // ""' <<<"$focused")
fullscreen=$(jq -r '.fullscreen // 0' <<<"$focused")
pinned=$(jq -r '.pinned // false' <<<"$focused")
state="$runtime/pip-fullscreen-$UID-${address}.pinned"
case "$title" in
  "Picture in picture"|"Picture-in-Picture"|"Picture in Picture")
    if [ "$fullscreen" = 0 ]; then
      rm -f "$state"
      if [ "$pinned" = true ]; then
        hyprctl dispatch pin "address:$address" >/dev/null
        touch "$state"
      fi
      hyprctl dispatch fullscreen 0 >/dev/null
    else
      hyprctl dispatch fullscreen 0 >/dev/null
      if [ -f "$state" ]; then
        if [ "$pinned" != true ]; then
          hyprctl dispatch pin "address:$address" >/dev/null
        fi
        rm -f "$state"
      fi
    fi
    ;;
  *) hyprctl dispatch fullscreen 0 >/dev/null ;;
esac
