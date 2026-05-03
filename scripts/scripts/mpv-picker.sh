#!/bin/bash
# Usage: ./mpv-picker.sh [watch_later|history]
MODE="${1:-history}"
WL_CACHE="$HOME/.cache/yt-watch-later.tsv"
WATCH_LOG="$HOME/.local/share/mpv-youtube-history.tsv"
THUMB_CACHE="$HOME/.cache/yt-thumbnails"
PIXMAPS="$HOME/.local/share/pixmaps"

# Fallback to a working icon (Bluebubbles or Shroud)
FALLBACK_ICON="/usr/share/pixmaps/bluebubbles.png"
[ ! -f "$FALLBACK_ICON" ] && FALLBACK_ICON="$PIXMAPS/shroud.png"

mkdir -p "$THUMB_CACHE" "$PIXMAPS"
exec >/tmp/mpv-picker.log 2>&1

# --- Helpers ---
update_wl_cache() {
  if [ -f "/tmp/yt-wl-fetch.lock" ]; then return; fi
  (
    touch "/tmp/yt-wl-fetch.lock"
    echo "Updating Watch Later cache..."
    yt-dlp --cookies-from-browser firefox \
      --flat-playlist --playlist-end 50 \
      --print "%(title)s	https://www.youtube.com/watch?v=%(id)s	%(uploader)s" \
      "https://www.youtube.com/playlist?list=WL" >"${WL_CACHE}.tmp" 2>/dev/null &&
      mv "${WL_CACHE}.tmp" "$WL_CACHE"
    rm "/tmp/yt-wl-fetch.lock"
  ) &
}

fetch_history() {
  {
    [[ -f "$WATCH_LOG" ]] && cat "$WATCH_LOG"
    if [[ -f "$HOME/.config/google-chrome/Default/History" ]]; then
      TMP_HIST=$(mktemp)
      cp "$HOME/.config/google-chrome/Default/History" "$TMP_HIST"
      sqlite3 "$TMP_HIST" "SELECT CAST((last_visit_time/1000000)-11644473600 AS INTEGER), title, url FROM urls WHERE url LIKE '%youtube.com/watch%' ORDER BY last_visit_time DESC LIMIT 50;" -separator $'\t' 2>/dev/null
      rm "$TMP_HIST"
    fi
  } | sort -rn | awk -F'\t' '!seen[$3]++' | head -50
}

# --- Build URL Map ---
URL_MAP=$(mktemp)
if [[ "$MODE" == "watch_later" ]]; then
  echo "SWITCH_TO_HISTORY" >"$URL_MAP"
  [ -f "$WL_CACHE" ] && cut -f2 "$WL_CACHE" >>"$URL_MAP"
  PROMPT="Watch Later ❯ "
  update_wl_cache
else
  echo "SWITCH_TO_WL" >"$URL_MAP"
  fetch_history | cut -f3 >>"$URL_MAP"
  PROMPT="YouTube History ❯ "
fi

# --- The Fuzzel Pipe ---
CHOICE=$({
  # Row 0: Switcher with standard system icon
  printf "Switch Mode\0icon\x1fview-refresh\n"

  # Get the data stream
  DATA=$([[ "$MODE" == "watch_later" ]] && cat "$WL_CACHE" 2>/dev/null || fetch_history)

  echo "$DATA" | while IFS=$'\t' read -r c1 c2 c3 c4; do
    # Column mapping varies by source
    if [[ "$MODE" == "watch_later" ]]; then
      URL="$c2"
      TITLE="$c1"
      CHAN="$c3"
    else
      URL="$c3"
      TITLE="$c2"
      CHAN="$c4"
    fi

    VIDEO_ID=$(echo "$URL" | grep -oP '(?<=v=)[^&]+')
    JPG_PATH="${THUMB_CACHE}/${VIDEO_ID}.jpg"
    PNG_PATH="${THUMB_CACHE}/${VIDEO_ID}.png"

    ICON="$FALLBACK_ICON"

    # Check and convert to PNG (Cairo/Fuzzel preferred format)
    if [ -f "$PNG_PATH" ]; then
      ICON="$PNG_PATH"
    elif [ -f "$JPG_PATH" ]; then
      # Resize to 256px wide for high-density displays (sharpness)
      magick "$JPG_PATH" -resize 256x "$PNG_PATH" && ICON="$PNG_PATH"
    else
      # Download and convert in background for next run
      (curl -s -L -o "$JPG_PATH" "https://img.youtube.com/vi/${VIDEO_ID}/mqdefault.jpg" &&
        magick "$JPG_PATH" -resize 256x "$PNG_PATH") &
    fi

    # Build the Fuzzel dmenu row (Label\0icon\x1fPath)
    printf "%s — %s\0icon\x1f%s\n" "${TITLE:0:60}" "${CHAN:-History}" "$ICON"
  done
} | fuzzel --dmenu --index --prompt "$PROMPT" --width 45 --lines 10 --line-height 35)

# --- Choice Execution ---
if [[ -n "$CHOICE" ]]; then
  # Grab the URL from the index map
  TARGET=$(sed "$((CHOICE + 1))q;d" "$URL_MAP")
  rm "$URL_MAP"

  if [[ "$TARGET" == "SWITCH_TO_HISTORY" ]]; then
    exec "$0" history
  elif [[ "$TARGET" == "SWITCH_TO_WL" ]]; then
    exec "$0" watch_later
  else
    pkill -f "mpv --ytdl-raw-options=cookies-from-browser=firefox"
    notify-send "MPV" "Opening Video..."
    # mpv --ytdl-raw-options=cookies-from-browser=firefox "$TARGET" &>/dev/null &
    # mpv --ytdl-raw-options="cookies-from-browser=firefox,format=bestvideo[height<=?1080]+bestaudio/best,no-check-certificates=,ignore-config=" \
    #   --cache=yes \
    #   --demuxer-max-bytes=124M \
    #   --demuxer-readahead-secs=30 \
    #   "$TARGET" &>/dev/null &
    # yt-dlp --cookies "$HOME/my_cookies.txt" \
    #   --format "bestvideo[height<=?1080]+bestaudio/best" \
    #   --no-playlist \
    #   --quiet --no-warnings \
    #   -o - "$TARGET" | mpv - --cache=yes --force-window=yes &>/dev/null &
    mpv --cache=yes --force-window=yes "$TARGET"
    echo $! >/tmp/mpv-yt-pid
    disown
  fi
else
  rm "$URL_MAP"
fi
