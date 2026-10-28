#!/bin/bash
# Shared fullscreen toggle for Mod+F and MPV F, preserving PiP pin state.
set -euo pipefail
runtime="${XDG_RUNTIME_DIR:-/tmp}"
exec 9>"$runtime/pip-fullscreen-$UID.lock"
flock -n 9 || exit 0
clients=$(hyprctl clients -j)
if [ "${1:-}" = "--pid" ]; then
  focused=$(jq -c --argjson pid "$2" '[.[] | select(.pid == $pid and .class == "mpv" and .mapped)] | first // {}' <<<"$clients")
else
  pointer=$(hyprctl cursorpos -j)
  workspace=$(hyprctl activeworkspace -j | jq '.id')
  # Prefer the video under the pointer, even if a pinned no-focus rule means
  # another application still owns keyboard focus.
  focused=$(jq -c --argjson p "$pointer" --argjson ws "$workspace" '
    [.[] | select(.mapped and (.hidden | not))
     | select(.pinned or .workspace.id == $ws)
     | select(.class == "mpv" or (.title | test("^Picture[- ]in[- ]picture$"; "i")))
     | select($p.x >= .at[0] and $p.x < (.at[0] + .size[0])
          and $p.y >= .at[1] and $p.y < (.at[1] + .size[1]))]
    | sort_by(if .focusHistoryID < 0 then 999999 else .focusHistoryID end)
    | first // empty' <<<"$clients")
  [ -n "$focused" ] || focused=$(hyprctl activewindow -j)
fi
address=$(jq -r '.address // empty' <<<"$focused")
[ -n "$address" ] || exit 0
title=$(jq -r '.title // ""' <<<"$focused")
fullscreen=$(jq -r '.fullscreen // 0' <<<"$focused")
pinned=$(jq -r '.pinned // false' <<<"$focused")
state="$runtime/pip-fullscreen-$UID-${address}.pinned"
class=$(jq -r '.class // ""' <<<"$focused")
pid=$(jq -r '.pid // 0' <<<"$focused")
case "$class:$title" in
  mpv:*|*:"Picture in picture"|*:"Picture-in-Picture"|*:"Picture in Picture")
    # Deliberate focus must work for pinned browser PiP as well as MPV.
    trap 'hyprctl dispatch setprop "address:$address no_focus unset" >/dev/null' EXIT
    hyprctl --batch "dispatch setprop address:$address no_focus 0; dispatch focuswindow address:$address" >/dev/null
    if [ "$fullscreen" = 0 ]; then
      # Capture geometry before unpinning/fullscreen changes it.
      geometry_state="$runtime/pip-fullscreen-$UID-${address}.geometry"
      printf '%s\n' "$focused" > "$geometry_state.tmp"
      mv -f "$geometry_state.tmp" "$geometry_state"
      # Keep a separate snapshot: the fallback watcher consumes .geometry.
      cp "$geometry_state" "$geometry_state.return"
      rm -f "$state"
      if [ "$pinned" = true ]; then
        hyprctl dispatch pin "address:$address" >/dev/null
        printf '%s\n' "$pid" > "$state"
      fi
      hyprctl dispatch fullscreen 0 >/dev/null
    else
      geometry_state="$runtime/pip-fullscreen-$UID-${address}.geometry"
      # Exit and restore before the compositor renders the next frame.
      restore=$(jq -r --argjson pid "$pid" --arg address "$address" '
        select(.pid == $pid and .floating == true)
        | "dispatch resizewindowpixel exact \(.size[0]) \(.size[1]),address:\($address); dispatch movewindowpixel exact \(.at[0]) \(.at[1]),address:\($address)"
      ' "$geometry_state.return" 2>/dev/null || true)
      if [ -n "$restore" ]; then
        hyprctl --batch "dispatch fullscreen 0; $restore" >/dev/null
        printf '%s\n' "$pid" > "$geometry_state.restored"
        rm -f "$geometry_state" "$geometry_state.return"
      else
        hyprctl dispatch fullscreen 0 >/dev/null
      fi
      if [ -f "$state" ] && [ "$(cat "$state")" = "$pid" ]; then
        if [ "$pinned" != true ]; then
          hyprctl dispatch pin "address:$address" >/dev/null
        fi
        rm -f "$state"
      fi
    fi
    ;;
  *) hyprctl dispatch fullscreen 0 >/dev/null ;;
esac
