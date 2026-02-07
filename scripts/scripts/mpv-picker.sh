#!/bin/bash
exec >/tmp/mpv-picker.log 2>&1
echo "Picker triggered at $(date)"
WATCH_LOG="$HOME/.local/share/mpv-youtube-history.tsv"
CHROME_HISTORY="$HOME/.config/google-chrome/Default/History"
THUMB_CACHE="$HOME/.cache/yt-thumbnails"
TMPDIR=$(mktemp -d)
MERGED="$TMPDIR/merged.tsv"

mkdir -p "$THUMB_CACHE"

# --- Source 1: mpv watch log ---
if [[ -f "$WATCH_LOG" ]]; then
  cp "$WATCH_LOG" "$TMPDIR/watchlog.tsv"
else
  touch "$TMPDIR/watchlog.tsv"
fi
# --- Source 2: Chrome history (YouTube only) ---
if [[ -f "$CHROME_HISTORY" ]]; then
  cp "$CHROME_HISTORY" "$TMPDIR/History"
  sqlite3 "$TMPDIR/History" "
    SELECT
      CAST((last_visit_time / 1000000) - 11644473600 AS INTEGER),
      title,
      url
    FROM urls
    WHERE url LIKE '%youtube.com/watch%' AND url NOT LIKE '%music.youtube.com%'
    ORDER BY last_visit_time DESC
    LIMIT 50;
  " -separator $'\t' >"$TMPDIR/chrome.tsv" 2>/dev/null
else
  touch "$TMPDIR/chrome.tsv"
fi
# --- Merge and deduplicate ---
cat "$TMPDIR/watchlog.tsv" "$TMPDIR/chrome.tsv" |
  awk -F'\t' '
  {
    match($3, /v=([^&]+)/, m)
    vid = m[1]
    if (vid != "" && (!(vid in seen) || $1 > ts[vid])) {
      seen[vid] = NR
      ts[vid] = $1
      title[vid] = $2
      url[vid] = $3
      channel[vid] = ($4 != "" ? $4 : "")
    }
  }
  END {
    n = asorti(ts, sorted)
    for (i = n; i >= 1; i--) {
      vid = sorted[i]
      printf "%s\t%s\t%s\t%s\n", ts[vid], title[vid], url[vid], channel[vid]
    }
  }' | sort -t$'\t' -k1 -rn | head -30 >"$MERGED"

# --- Download thumbnails ---
while IFS=$'\t' read -r ts title url channel; do
  VIDEO_ID=$(echo "$url" | grep -oP '(?<=v=)[^&]+')
  THUMB_PATH="$THUMB_CACHE/${VIDEO_ID}.jpg"
  if [ -n "$VIDEO_ID" ] && [ ! -f "$THUMB_PATH" ]; then
    curl -s -o "$THUMB_PATH" "https://img.youtube.com/vi/${VIDEO_ID}/mqdefault.jpg" &
  fi
done <"$MERGED"

# --- Build display list ---
MENU_ENTRIES=""
URL_MAP=""
while IFS=$'\t' read -r ts title url channel; do
  NOW=$(date +%s)
  AGO=$(((NOW - ts) / 60))
  if ((AGO < 60)); then
    TIME_STR="${AGO}m ago"
  elif ((AGO < 1440)); then
    TIME_STR="$((AGO / 60))h ago"
  else
    TIME_STR="$((AGO / 1440))d ago"
  fi
  SHORT_TITLE="${title:0:55}"
  [[ ${#title} -gt 55 ]] && SHORT_TITLE="${SHORT_TITLE}..."

  VIDEO_ID=$(echo "$url" | grep -oP '(?<=v=)[^&]+')
  THUMB_PATH="$THUMB_CACHE/${VIDEO_ID}.jpg"

  if [[ -n "$channel" ]]; then
    LABEL="${SHORT_TITLE} — ${channel}  (${TIME_STR})"
  else
    LABEL="${SHORT_TITLE}  (${TIME_STR})"
  fi

  if [ -f "$THUMB_PATH" ]; then
    MENU_ENTRIES+="img:${THUMB_PATH}:text:${LABEL}\t${url}\n"
  else
    MENU_ENTRIES+="${LABEL}\t${url}\n"
  fi
done <"$MERGED"

if [[ -z "$MENU_ENTRIES" ]]; then
  notify-send "MPV" "No YouTube history found"
  rm -rf "$TMPDIR"
  exit 1
fi
# --- Show picker ---
if command -v wofi &>/dev/null; then
  CHOICE=$(echo -e "$MENU_ENTRIES" | awk -F'\t' '{print $1}' |
    wofi --dmenu --prompt "YouTube History" --width 800 --lines 15 --allow-images)
elif command -v rofi &>/dev/null; then
  CHOICE=$(echo -e "$MENU_ENTRIES" | awk -F'\t' '{print $1}' |
    rofi -dmenu -p "YouTube History" -width 800 -lines 15)
else
  notify-send "Error" "No picker found (install wofi or rofi)"
  rm -rf "$TMPDIR"
  exit 1
fi
if [[ -z "$CHOICE" ]]; then
  rm -rf "$TMPDIR"
  exit 0
fi
# --- Find the URL for the chosen entry ---
# Strip the image prefix for matching
CLEAN_CHOICE=$(echo "$CHOICE" | sed 's/.*:text://')
URL=$(echo -e "$MENU_ENTRIES" | grep -F "$CLEAN_CHOICE" | head -1 | awk -F'\t' '{print $2}')

if [[ -n "$URL" ]]; then
  VIDEO_ID=$(echo "$URL" | grep -oP '(?<=v=)[^&]+')
  TITLE=$(echo "$CLEAN_CHOICE" | sed 's/ — .*//')
  CHANNEL=$(echo "$CLEAN_CHOICE" | sed -n 's/.*— \(.*\)  ([0-9]*[dhm] ago)/\1/p')
  TIMESTAMP=$(date +%s)
  if [[ -f "$WATCH_LOG" ]]; then
    grep -v "$VIDEO_ID" "$WATCH_LOG" >"${WATCH_LOG}.tmp" && mv "${WATCH_LOG}.tmp" "$WATCH_LOG"
  fi
  echo -e "${TIMESTAMP}\t${TITLE}\t${URL}\t${CHANNEL}" >>"$WATCH_LOG"
  echo "YT_URL=\"$URL\"" >/tmp/youtube-stream-context.conf
  if [ -f "$THUMB_CACHE/${VIDEO_ID}.jpg" ]; then
    notify-send -i "$THUMB_CACHE/${VIDEO_ID}.jpg" "MPV" "Resuming: ${TITLE}"
  else
    notify-send "MPV" "Resuming: ${TITLE}"
  fi
  pkill streamlink && mpv --ytdl-raw-options=cookies-from-browser=firefox "$URL" &
else
  notify-send "Error" "Could not find URL"
fi
rm -rf "$TMPDIR"
