#!/bin/bash
# Keep the YouTube webapp tab numbers contiguous.
#
# Numbers come from document.title (see yt-tab-numbers.py). Closing a tab does
# not renumber the rest on its own, so closing 2 of 1/2/3 would leave 1 and 3.
# This listens on Hyprland's event socket and renumbers whenever a window opens
# or closes, which is cheap and avoids polling.

SOCK="$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock"
[ -S "$SOCK" ] || exit 1

renumber() {
  # Debounce: closing a window emits several events, and the compositor needs a
  # moment before the group membership reflects the change.
  sleep 0.4
  "$HOME/scripts/yt-tab-numbers.py" >/dev/null 2>&1
}

socat -U - "UNIX-CONNECT:$SOCK" 2>/dev/null | while read -r line; do
  case "$line" in
  closewindow*|openwindow*)
    sleep 0.4
    # Only bother renumbering when a webapp window is actually present.
    if hyprctl clients -j 2>/dev/null | jq -e '.[] | select(.class | test("brave-(www\\.)?youtube\\.com"))' >/dev/null 2>&1; then
      renumber
    fi
    ;;
  esac
done
