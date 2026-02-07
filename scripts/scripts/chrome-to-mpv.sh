#!/bin/bash
exec >/tmp/chrome-to-mpv.log 2>&1
echo "Script triggered at $(date)"
WATCH_LOG="$HOME/.local/share/mpv-youtube-history.tsv"
mkdir -p "$(dirname "$WATCH_LOG")"

ACTIVE_CLASS=$(hyprctl activewindow -j | jq -r '.class')

if [[ "$ACTIVE_CLASS" == "google-chrome" ]]; then
  # Wait for triggering keybind to be released
  sleep 0.5
  wl-copy --clear
  wtype -M ctrl l -m ctrl
  sleep 0.1
  wtype -M ctrl c -m ctrl
  sleep 0.1
  URL=$(wl-paste)
  echo "Captured URL: $URL"
  wtype -k Escape
fi

if [[ -n "$URL" ]] && [[ "$URL" != *"music.youtube.com"* ]] && { [[ "$URL" == *"youtube.com"* ]] || [[ "$URL" == *"youtu.be"* ]]; }; then
  CLEAN_URL="${URL//&list=*/}"
  CLEAN_URL=$(echo "$CLEAN_URL" | sed 's/&index=[^&]*//g; s/&si=[^&]*//g')
  VIDEO_ID="${CLEAN_URL##*v=}"
  VIDEO_ID="${VIDEO_ID%%&*}"

  echo "YT_URL=\"$CLEAN_URL\"" >/tmp/youtube-stream-context.conf

  # Kill previous mpv instance by saved PID
  if [ -f /tmp/mpv-yt-pid ]; then
    kill $(cat /tmp/mpv-yt-pid) 2>/dev/null
    sleep 0.3
  fi
  mpv --ytdl-raw-options=cookies-from-browser=firefox "$URL" &>/dev/null &
  echo $! >/tmp/mpv-yt-pid
  disown
  # Launch mpv IMMEDIATELY — this is the priority
  # mpv --ytdl-raw-options=cookies-from-browser=firefox "$CLEAN_URL" &
  # disown

  # Notify and log in background — don't block
  notify-send "MPV" "Opening in MPV..." &

  (
    INFO=$(yt-dlp --cookies-from-browser firefox --print "%(title)s	%(channel)s" "$CLEAN_URL" 2>/dev/null)
    TITLE="${INFO%%	*}"
    CHANNEL="${INFO#*	}"
    TITLE="${TITLE:-Unknown Title}"
    CHANNEL="${CHANNEL:-Unknown Channel}"
    TIMESTAMP=$(date +%s)
    if [[ -f "$WATCH_LOG" ]]; then
      grep -v "$VIDEO_ID" "$WATCH_LOG" >"${WATCH_LOG}.tmp" && mv "${WATCH_LOG}.tmp" "$WATCH_LOG"
    fi
    printf '%s\t%s\t%s\t%s\n' "$TIMESTAMP" "$TITLE" "$CLEAN_URL" "$CHANNEL" >>"$WATCH_LOG"
  ) &
else
  exec "$HOME/scripts/mpv-picker.sh"
fi
