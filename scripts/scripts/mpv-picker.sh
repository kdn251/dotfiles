#!/bin/bash
# YouTube history picker — shows recent YouTube videos from Chrome history
# and your mpv watch log, lets you pick one to resume in mpv.

exec >/tmp/mpv-picker.log 2>&1
echo "Picker triggered at $(date)"

WATCH_LOG="$HOME/.local/share/mpv-youtube-history.tsv"
CHROME_HISTORY="$HOME/.config/google-chrome/Default/History"
TMPDIR=$(mktemp -d)
MERGED="$TMPDIR/merged.tsv"

# --- Source 1: mpv watch log ---
if [[ -f "$WATCH_LOG" ]]; then
  cp "$WATCH_LOG" "$TMPDIR/watchlog.tsv"
else
  touch "$TMPDIR/watchlog.tsv"
fi

# --- Source 2: Chrome history (YouTube only) ---
if [[ -f "$CHROME_HISTORY" ]]; then
  # Chrome locks the DB, so copy it
  cp "$CHROME_HISTORY" "$TMPDIR/History"

  # Chrome timestamps are microseconds since 1601-01-01
  # Convert to unix epoch: subtract 11644473600 seconds
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

# --- Merge and deduplicate (prefer most recent entry per video ID) ---
cat "$TMPDIR/watchlog.tsv" "$TMPDIR/chrome.tsv" |
  awk -F'\t' '
  {
    # Extract video ID from URL
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

# --- Build display list ---
# Show: "title" with relative time
MENU_ENTRIES=""
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

  # Truncate long titles
  SHORT_TITLE="${title:0:55}"
  [[ ${#title} -gt 55 ]] && SHORT_TITLE="${SHORT_TITLE}..."

  # Format: "Title — Channel  (2h ago)"
  if [[ -n "$channel" ]]; then
    MENU_ENTRIES+="${SHORT_TITLE} — ${channel}  (${TIME_STR})\t${url}\n"
  else
    MENU_ENTRIES+="${SHORT_TITLE}  (${TIME_STR})\t${url}\n"
  fi
done <"$MERGED"

if [[ -z "$MENU_ENTRIES" ]]; then
  notify-send "MPV" "No YouTube history found"
  rm -rf "$TMPDIR"
  exit 1
fi

# --- Show picker (try wofi first, fall back to rofi) ---
if command -v wofi &>/dev/null; then
  CHOICE=$(echo -e "$MENU_ENTRIES" | awk -F'\t' '{print $1}' |
    wofi --dmenu --prompt "YouTube History" --width 800 --lines 15)
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
URL=$(echo -e "$MENU_ENTRIES" | grep -F "$CHOICE" | head -1 | awk -F'\t' '{print $2}')

if [[ -n "$URL" ]]; then
  # Log it to watch history
  VIDEO_ID=$(echo "$URL" | grep -oP '(?<=v=)[^&]+')
  TITLE=$(echo "$CHOICE" | sed 's/ — .*//')
  CHANNEL=$(echo "$CHOICE" | sed -n 's/.*— \(.*\)  ([0-9]*[dhm] ago)/\1/p')
  TIMESTAMP=$(date +%s)

  if [[ -f "$WATCH_LOG" ]]; then
    grep -v "$VIDEO_ID" "$WATCH_LOG" >"${WATCH_LOG}.tmp" && mv "${WATCH_LOG}.tmp" "$WATCH_LOG"
  fi
  echo -e "${TIMESTAMP}\t${TITLE}\t${URL}\t${CHANNEL}" >>"$WATCH_LOG"

  echo "YT_URL=\"$URL\"" >/tmp/youtube-stream-context.conf
  notify-send "MPV" "Resuming: ${TITLE}"
  mpv --ytdl-raw-options=cookies-from-browser=firefox "$URL" &
else
  notify-send "Error" "Could not find URL"
fi

rm -rf "$TMPDIR"
