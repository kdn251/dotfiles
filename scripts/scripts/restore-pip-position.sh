#!/bin/bash
# restore-pip-position.sh
#
# Workaround for a Hyprland regression (since v0.54): when a *floating* window
# leaves fullscreen, Hyprland re-centers it instead of restoring the position it
# had before. The upstream fix (PR #13500, shipped in 0.55.x) is unreliable for
# *pinned* windows -- which is exactly how our mpv / YouTube picture-in-picture
# floats run -- so they still jump to the centre intermittently.
#
# Why a cache is unavoidable (verified on 0.55.4):
#   * While a window is fullscreen, `hyprctl clients` reports the MONITOR
#     geometry -- the old floating position is not stored anywhere queryable.
#   * The socket2 `fullscreen>>1` event fires only AFTER geometry is already
#     swapped to the monitor size, so it is too late to read the old position.
#   So we continuously remember each PiP window's floating geometry while it is
#   NOT fullscreen, and re-apply it the instant `fullscreen>>0` arrives.
#
# This catches every way fullscreen gets toggled: mpv's `f`, the player's own
# fullscreen button, and the mod+f keybind (toggle-pip-fullscreen.sh).

set -u

SOCK="${XDG_RUNTIME_DIR}/hypr/${HYPRLAND_INSTANCE_SIGNATURE}/.socket2.sock"

# The only windows we ever touch: mpv floats and browser Picture-in-Picture.
# (Brave/Chrome title the PiP "Picture in picture"; some report "Picture-in-Picture".)
PIP_FILTER='.class=="mpv" or .title=="Picture in picture" or .title=="Picture-in-Picture"'

# Single instance only -- exec-once already guards this, but be safe if run by hand.
if [ "${PIP_RESTORE_LOCKED:-}" != "1" ]; then
  exec env PIP_RESTORE_LOCKED=1 flock -n "/tmp/restore-pip-position.lock" "$0" "$@"
fi

declare -A POS   # address -> "x y w h"  (last known floating geometry)

# Cache the floating geometry of every floating, non-fullscreen PiP window.
refresh_cache() {
  local addr fs floating x y w h
  while IFS=$'\t' read -r addr fs floating x y w h; do
    [ "$floating" = "true" ] || continue   # ignore tiled mpv (handled fine by Hyprland)
    [ "$fs" = "0" ]          || continue   # never cache fullscreen (= monitor) geometry
    POS["$addr"]="$x $y $w $h"
  done < <(hyprctl clients -j | jq -r "
    .[] | select($PIP_FILTER)
    | [ .address, (.fullscreen|tostring), (.floating|tostring),
        (.at[0]|tostring), (.at[1]|tostring),
        (.size[0]|tostring), (.size[1]|tostring) ] | @tsv")
}

# A window just left fullscreen; if it is a PiP we have cached, snap it back.
restore_exited() {
  local addr fs cached x y w h
  # The window that just un-fullscreened is the focused one.
  IFS=$'\t' read -r addr fs < <(hyprctl activewindow -j \
    | jq -r '[.address,(.fullscreen|tostring)]|@tsv')
  [ -n "${addr:-}" ] || return
  [ "$fs" = "0" ]    || return            # somehow still fullscreen -> bail
  cached="${POS[$addr]:-}"
  [ -n "$cached" ]   || return            # not a window we cached -> leave it alone
  read -r x y w h <<<"$cached"
  hyprctl --batch \
    "dispatch resizewindowpixel exact $w $h,address:$addr ; dispatch movewindowpixel exact $x $y,address:$addr" \
    >/dev/null
}

[ -S "$SOCK" ] || { echo "restore-pip-position: no socket2 at $SOCK" >&2; exit 1; }

# Seed the cache, then react to events. `read -t 1` gives a ~1s idle tick that
# keeps the cache fresh (catching manual drags) without busy-polling.
refresh_cache
exec 3< <(exec socat -u UNIX-CONNECT:"$SOCK" -)
while true; do
  if IFS= read -t 1 -r line <&3; then
    case "$line" in
      fullscreen\>\>0) restore_exited ;;   # a window left fullscreen
      *) : ;;
    esac
  else
    refresh_cache                          # idle: remember latest floating positions
  fi
done
