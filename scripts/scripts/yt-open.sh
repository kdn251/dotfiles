#!/bin/bash
# Open a YouTube link in the webapp.  yt-open.sh [URL]
#
# With no argument it reads the clipboard, which covers the usual case: someone
# sends a link, you copy it, you press the hotkey.
#
# App-mode windows have no address bar, so a link cannot be typed or pasted in
# the normal way. If the webapp is already running this navigates it in place
# over CDP (same window, keeps the session); otherwise it launches the webapp
# on that URL.

REPLACE=0
[ "$1" = "--replace" ] && { REPLACE=1; shift; }

URL="${1:-}"
[ -z "$URL" ] && URL=$(wl-paste 2>/dev/null)
URL=$(printf '%s' "$URL" | tr -d '[:space:]')

if [ -z "$URL" ]; then
  notify-send -a "YT" -u low -t 3000 "YouTube" "Clipboard is empty."
  exit 1
fi

# youtu.be/<id>?t=90 -> youtube.com/watch?v=<id>&t=90 so timestamps survive.
case "$URL" in
*youtu.be/*)
  id=${URL##*youtu.be/}
  rest=""
  case "$id" in *\?*) rest="&${id#*\?}"; id="${id%%\?*}" ;; esac
  URL="https://www.youtube.com/watch?v=${id}${rest}"
  ;;
esac

case "$URL" in
http*youtube.com/* | http*youtu.be/*) ;;
*)
  notify-send -a "YT" -u low -t 3000 "YouTube" "Not a YouTube link:
${URL:0:60}"
  exit 1
  ;;
esac

# Default is a NEW tab, so the video you are already watching is not replaced.
# `--replace` navigates the current one in place instead.
#
# The windows become tabs through Hyprland's window groups (app-mode windows
# have no tab strip). The group rule adds an opening window to the FOCUSED
# window's group, so an existing webapp window is focused first -- otherwise
# the new one starts a group of its own wherever focus happened to be.
EXISTING=$(hyprctl clients -j 2>/dev/null |
  jq -r '.[] | select(.class | test("brave.*youtube")) | .address' | head -1)

if [ "$REPLACE" = 1 ] && [ -n "$EXISTING" ]; then
  if "$HOME/scripts/yt-pip-cdp.py" --open "$URL" >/dev/null 2>&1; then
    hyprctl dispatch focuswindow "address:$EXISTING" >/dev/null 2>&1
    exit 0
  fi
fi

[ -n "$EXISTING" ] && {
  hyprctl dispatch focuswindow "address:$EXISTING" >/dev/null 2>&1
  sleep 0.3
}
# Renumber once the new window exists, so the groupbar tabs stay 1..N.
( sleep 6; "$HOME/scripts/yt-tab-numbers.py" >/dev/null 2>&1 ) &
exec "$HOME/scripts/yt-webapp.sh" "$URL"
