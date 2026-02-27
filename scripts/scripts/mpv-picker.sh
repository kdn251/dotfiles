#!/bin/bash
# Usage: ./mpv-picker.sh [watch_later|history]
MODE="${1:-watch_later}"
WL_CACHE="$HOME/.cache/yt-watch-later.tsv"
WATCH_LOG="$HOME/.local/share/mpv-youtube-history.tsv"
THUMB_CACHE="$HOME/.cache/yt-thumbnails"
LOCK_FILE="/tmp/yt-wl-fetch.lock"

mkdir -p "$THUMB_CACHE"
exec >/tmp/mpv-picker.log 2>&1

# --- Background Cache Update ---
update_wl_cache() {
  # Don't start a second fetch if one is already running
  if [ -f "$LOCK_FILE" ]; then return; fi

  (
    touch "$LOCK_FILE"
    echo "Updating Watch Later cache..."
    yt-dlp --cookies-from-browser firefox \
      --flat-playlist --playlist-end 50 \
      --print "%(title)s	https://www.youtube.com/watch?v=%(id)s	%(uploader)s" \
      "https://www.youtube.com/playlist?list=WL" >"${WL_CACHE}.tmp" 2>/dev/null &&
      mv "${WL_CACHE}.tmp" "$WL_CACHE"
    rm "$LOCK_FILE"
  ) &
}

fetch_history() {
  {
    [[ -f "$WATCH_LOG" ]] && cat "$WATCH_LOG"
    if [[ -f "$HOME/.config/google-chrome/Default/History" ]]; then
      TMP_HIST=$(mktemp)
      cp "$HOME/.config/google-chrome/Default/History" "$TMP_HIST"
      sqlite3 "$TMP_HIST" "
            SELECT CAST((last_visit_time / 1000000) - 11644473600 AS INTEGER), title, url
            FROM urls WHERE url LIKE '%youtube.com/watch%' 
            ORDER BY last_visit_time DESC LIMIT 50;" -separator $'\t' 2>/dev/null
      rm "$TMP_HIST"
    fi
  } | sort -t$'\t' -k1 -rn | awk -F'\t' '!seen[$3]++' | head -50
}

# --- Build the List ---
MENU_BODY=""

if [[ "$MODE" == "watch_later" ]]; then
  PROMPT="Watch Later"
  SWITCH_LABEL="󰄮 SWITCH TO HISTORY"
  SWITCH_ACTION="GOTO_HISTORY"

  # Trigger the background update every time, but show cache immediately
  update_wl_cache

  if [[ -f "$WL_CACHE" ]]; then
    while IFS=$'\t' read -r title url channel; do
      VIDEO_ID=$(echo "$url" | grep -oP '(?<=v=)[^&]+')
      LABEL="${title:0:60} — ${channel}"
      MENU_BODY+="img:${THUMB_CACHE}/${VIDEO_ID}.jpg:text:${LABEL}\t${url}\n"
      # Background download thumbs if missing
      [[ ! -f "${THUMB_CACHE}/${VIDEO_ID}.jpg" ]] && curl -s -L -o "${THUMB_CACHE}/${VIDEO_ID}.jpg" "https://img.youtube.com/vi/${VIDEO_ID}/mqdefault.jpg" &
    done <"$WL_CACHE"
  else
    MENU_BODY="Fetching Watch Later for the first time... Close and re-open in 5s.\tRETRY\n"
  fi
else
  PROMPT="YouTube History"
  SWITCH_LABEL="󰄮 SWITCH TO WATCH LATER"
  SWITCH_ACTION="GOTO_WL"

  while IFS=$'\t' read -r ts title url channel; do
    VIDEO_ID=$(echo "$url" | grep -oP '(?<=v=)[^&]+')
    LABEL="${title:0:60} (${channel:-History})"
    MENU_BODY+="img:${THUMB_CACHE}/${VIDEO_ID}.jpg:text:${LABEL}\t${url}\n"
    [[ ! -f "${THUMB_CACHE}/${VIDEO_ID}.jpg" ]] && curl -s -L -o "${THUMB_CACHE}/${VIDEO_ID}.jpg" "https://img.youtube.com/vi/${VIDEO_ID}/mqdefault.jpg" &
  done <<<"$(fetch_history)"
fi

# --- Assembly: Switch is ALWAYS at index 0 ---
FINAL_MENU="${SWITCH_LABEL}\t${SWITCH_ACTION}\n${MENU_BODY}"

# --- Show Picker ---
CHOICE=$(echo -e "$FINAL_MENU" | awk -F'\t' '{print $1}' |
  wofi --dmenu --prompt "$PROMPT" --width 900 --lines 15 --allow-images)

[[ -z "$CHOICE" ]] && exit 0

# Match the label back to the URL/Action
FINAL_TARGET=$(echo -e "$FINAL_MENU" | grep -F -m 1 "$CHOICE" | awk -F'\t' '{print $2}')

case "$FINAL_TARGET" in
GOTO_HISTORY) exec "$0" history ;;
GOTO_WL) exec "$0" watch_later ;;
RETRY)
  sleep 0.5
  exec "$0" watch_later
  ;;
*)
  if [[ -n "$FINAL_TARGET" ]]; then
    notify-send "MPV" "Opening Video..."
    # Cleanly kill existing mpv instances
    pkill -f "mpv --ytdl-raw-options=cookies-from-browser=firefox"
    mpv --ytdl-raw-options=cookies-from-browser=firefox "$FINAL_TARGET" &>/dev/null &
    echo $! >/tmp/mpv-yt-pid
    disown
  fi
  ;;
esac
