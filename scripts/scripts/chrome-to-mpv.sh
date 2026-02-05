#!/bin/bash
# Log everything
exec >/tmp/mpv-yoink.log 2>&1
echo "Script triggered at $(date)"

# 1. Clear clipboard and grab URL
wl-copy --clear
hyprctl dispatch focuswindow 'class:^(google-chrome)$'
sleep 0.4
wtype -M ctrl l -m ctrl
sleep 0.2
wtype -M ctrl c -m ctrl
sleep 0.3
URL=$(wl-paste)
sleep 0.3
wtype -k F6
echo "Captured URL: $URL"

# 2. Launch in mpv
if [[ "$URL" == *"youtube.com"* ]] || [[ "$URL" == *"youtu.be"* ]]; then
  notify-send "MPV" "Opening in MPV..."
  mpv --ytdl-raw-options=cookies-from-browser=firefox "$URL" &
else
  notify-send "Error" "No YouTube URL found"
fi
