#!/bin/bash
exec >/tmp/chrome-to-mpv.log 2>&1
WATCH_LOG="$HOME/.local/share/mpv-youtube-history.tsv"

ACTIVE_CLASS=$(hyprctl activewindow -j | jq -r '.class')

if [[ "$ACTIVE_CLASS" == "google-chrome" ]]; then
  sleep 0.5
  wl-copy --clear
  wtype -M ctrl l -m ctrl
  sleep 0.1
  wtype -M ctrl c -m ctrl
  sleep 0.1
  URL=$(wl-paste)
  wtype -k Escape
fi

if [[ -n "$URL" ]] && [[ "$URL" == *"youtube.com"* ]]; then
  # Play the URL immediately
  pkill mpv
  mpv --ytdl-raw-options=cookies-from-browser=firefox "$URL" &
  disown
  notify-send "MPV" "Opening Video..."
else
  # THIS IS THE PART THAT CALLS THE PICKER
  # Make sure this path is correct for your machine
  exec "$HOME/scripts/mpv-picker.sh" history
fi
