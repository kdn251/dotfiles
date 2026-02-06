#!/bin/bash
# Log everything
exec >/tmp/chrome-to-mpv.log 2>&1
echo "Script triggered at $(date)"
WATCH_LOG="$HOME/.local/share/mpv-youtube-history.tsv"
mkdir -p "$(dirname "$WATCH_LOG")"
# 1. Clear clipboard and grab URL
wl-copy --clear
hyprctl dispatch focuswindow 'class:^(google-chrome)$'
sleep 0.4
wtype -M ctrl l -m ctrl
sleep 0.2
wtype -M ctrl c -m ctrl
sleep 0.3
URL=$(wl-paste)
echo "Captured URL: $URL"
# Deselect the address bar
sleep 0.2
hyprctl dispatch focuswindow 'class:^(google-chrome)$'
sleep 0.1
wtype -k Escape
sleep 0.1
wtype -k Escape
# 2. Launch in mpv
if [[ "$URL" != *"music.youtube.com"* ]] && { [[ "$URL" == *"youtube.com"* ]] || [[ "$URL" == *"youtu.be"* ]]; }; then
  CLEAN_URL=$(echo "$URL" | sed 's/&list=[^&]*//g; s/&index=[^&]*//g; s/&si=[^&]*//g')
  VIDEO_ID=$(echo "$CLEAN_URL" | grep -oP '(?<=v=)[^&]+')
  notify-send "MPV" "Opening in MPV..."
  # Launch mpv immediately
  sleep 0.5
  mpv --ytdl-raw-options=cookies-from-browser=firefox "$CLEAN_URL" &
  disown
  # Log title and channel in the background (don't block mpv)
  (
    INFO=$(yt-dlp --cookies-from-browser firefox --print "%(title)s	%(channel)s" "$CLEAN_URL" 2>/dev/null)
    TITLE=$(echo "$INFO" | cut -f1)
    CHANNEL=$(echo "$INFO" | cut -f2)
    TITLE=${TITLE:-"Unknown Title"}
    CHANNEL=${CHANNEL:-"Unknown Channel"}
    TIMESTAMP=$(date +%s)
    if [[ -f "$WATCH_LOG" ]]; then
      grep -v "$VIDEO_ID" "$WATCH_LOG" >"${WATCH_LOG}.tmp" && mv "${WATCH_LOG}.tmp" "$WATCH_LOG"
    fi
    echo -e "${TIMESTAMP}\t${TITLE}\t${CLEAN_URL}\t${CHANNEL}" >>"$WATCH_LOG"
  ) &
else
  notify-send "Error" "No YouTube URL found"
fi
