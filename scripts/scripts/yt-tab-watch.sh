#!/bin/bash
# Keep the YouTube webapp tab numbers contiguous.
#
# Numbers come from document.title (see yt-tab-numbers.py). Closing a tab does
# not renumber the rest on its own, so closing 2 of 1/2/3 would leave 1 and 3.
# This listens on Hyprland's event socket and renumbers whenever a window opens
# or closes, which is cheap and avoids polling.

SOCK="$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock"
[ -S "$SOCK" ] || exit 1

# Hyprland has no "hide the bar when there is only one tab" option, so the bar
# is toggled at runtime instead. Note group:groupbar:enabled is GLOBAL -- it
# applies to every group, not just the YouTube one. That is fine while these
# are the only groups in use; revisit if other groups appear.
sync_groupbar() {
  local biggest
  biggest=$(hyprctl clients -j 2>/dev/null | jq '[.[] | (.grouped | length)] | max // 0')
  if [ "${biggest:-0}" -gt 1 ]; then
    hyprctl keyword group:groupbar:enabled 1 >/dev/null 2>&1
  else
    hyprctl keyword group:groupbar:enabled 0 >/dev/null 2>&1
  fi
}

renumber() {
  # Debounce: closing a window emits several events, and the compositor needs a
  # moment before the group membership reflects the change.
  sleep 0.4
  "$HOME/scripts/yt-tab-numbers.py" >/dev/null 2>&1
}

sync_groupbar

socat -U - "UNIX-CONNECT:$SOCK" 2>/dev/null | while read -r line; do
  case "$line" in
  closewindow*|openwindow*)
    sleep 0.4
    sync_groupbar
    # Only bother renumbering when a webapp window is actually present.
    if hyprctl clients -j 2>/dev/null | jq -e '.[] | select(.class | test("youtube"))' >/dev/null 2>&1; then
      renumber
    fi
    ;;
  esac
done
