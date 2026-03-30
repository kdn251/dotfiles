#!/bin/bash
# Clear log for fresh run
echo "--- Starting Script $(date) ---" >/tmp/chrome-to-mpv.log
exec >>/tmp/chrome-to-mpv.log 2>&1

ACTIVE_CLASS=$(hyprctl activewindow -j | jq -r '.class')

if [[ "$ACTIVE_CLASS" == "google-chrome" || "$ACTIVE_CLASS" == "brave-browser" ]]; then
  # 1. Prepare
  wl-copy --clear
  sleep 0.2 # Give the hotkey time to "release"

  # 2. Force Highlight URL (Trying twice if needed)
  for i in {1..2}; do
    wtype -M ctrl -k l -m ctrl
    sleep 0.2
  done

  # 3. Force Copy URL
  wtype -M ctrl -k c -m ctrl
  sleep 0.3

  # 4. Clipboard Loop (with status prints)
  for i in {1..15}; do
    URL=$(wl-paste)
    if [[ -n "$URL" ]]; then
      echo "Successfully copied: $URL"
      break
    fi
    echo "Attempt $i: Nothing in clipboard yet..."
    sleep 0.1
  done

  # 5. UI Cleanup
  wtype -k Escape
  sleep 0.1

  # 6. Pause (Only if we got a URL)
  if [[ "$URL" == *"youtube.com/watch"* || "$URL" == *"youtu.be/"* ]]; then
    wtype -k space
  fi
fi

# 7. Final Logic
if [[ -n "$URL" ]] && [[ "$URL" == *"youtube.com/watch"* || "$URL" == *"youtu.be/"* ]]; then
  pkill -f "mpv --ytdl-raw-options=cookies-from-browser=firefox"
  notify-send "MPV" "Opening Video..." -t 2000
  mpv --ytdl-raw-options=cookies-from-browser=firefox "$URL" &
  disown
else
  echo "No URL found, falling back to picker."
  exec "$HOME/scripts/mpv-picker.sh" history
fi
