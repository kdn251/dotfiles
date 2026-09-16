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

if hyprctl clients -j 2>/dev/null | jq -e '.[] | select(.class | test("brave-youtube"))' >/dev/null; then
  # Reuse the running window rather than opening a second one.
  if "$HOME/scripts/yt-pip-cdp.py" --open "$URL" >/dev/null 2>&1; then
    hyprctl clients -j 2>/dev/null |
      jq -r '.[] | select(.class | test("brave-youtube")) | .address' | head -1 |
      while read -r a; do hyprctl dispatch focuswindow "address:$a" >/dev/null 2>&1; done
    exit 0
  fi
fi

exec "$HOME/scripts/yt-webapp.sh" "$URL"
