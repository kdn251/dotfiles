#!/bin/bash

# ==============================================================================
# CONFIGURATION
# ==============================================================================
BASE_VIDEO_DIR="$HOME/Videos/newsboat"
TWITCH_VOD_DIR="$BASE_VIDEO_DIR/twitch-vods"
ARCHIVE_FILE="$BASE_VIDEO_DIR/.downloaded-twitch-vods"
TWITCH_TOKEN=$(cat ~/.newsboat/.twitch_oauth 2>/dev/null)
WAYBAR_STATUS_FILE="/tmp/twitch_vod_status.txt"

STREAMERS=(
  "zackrawrr"
  "xqc"
  "aydan"
  "shroud"
  "jynxzi"
  "ohnePixel"
)

# ==============================================================================
# FUNCTIONS
# ==============================================================================

write_status() {
  local main_text="$1"
  local tooltip_text="$2"
  if [ -z "$main_text" ]; then
    echo " " >"$WAYBAR_STATUS_FILE"
  else
    printf "%s\n%s" "$main_text" "$tooltip_text" >"$WAYBAR_STATUS_FILE"
  fi
}

cleanup() {
  write_status "" "Twitch VOD Downloader inactive."
}

trap cleanup EXIT SIGINT SIGTERM

is_streamer_live() {
  local streamer=$1
  # Streamlink check for live status
  streamlink "https://www.twitch.tv/$streamer" best --json 2>&1 | grep -q '"error"'
  if [ $? -eq 0 ]; then
    return 1 # Not live
  else
    return 0 # Live
  fi
}

download_vods() {
  local streamer=$1

  write_status "$streamer" "Checking if $streamer is live or has new VODs."

  if is_streamer_live "$streamer"; then
    echo "Skipping $streamer - currently live (will download VOD later)"
    notify-send "Twitch VOD Downloader" "Skipping $streamer - currently live" -t 3000 -u low
    return
  fi

  # UPDATED: Added filter=archives and sort=time for better reliability
  VOD_URL=$(yt-dlp --flat-playlist --print url --playlist-end 1 "https://www.twitch.tv/$streamer/videos?filter=archives&sort=time" 2>/dev/null)

  # CRITICAL CHECK: Exit if no URL was found to prevent Streamlink errors
  if [ -z "$VOD_URL" ]; then
    echo "No VODs found for $streamer. Skipping."
    return
  fi

  VOD_ID=$(echo "$VOD_URL" | grep -oP 'videos/\K[0-9]+')

  if grep -q "^${streamer}:${VOD_ID}$" "$ARCHIVE_FILE"; then
    echo "Most recent VOD already recorded in archive: $VOD_ID"
    return
  fi

  VOD_TITLE=$(yt-dlp --get-title "$VOD_URL" 2>/dev/null || echo "Unknown VOD")

  if [[ "$VOD_TITLE" =~ \#[Aa]d ]]; then
    echo "Skipping $streamer VOD - contains #ad/#Ad in title"
    notify-send "Twitch VOD Downloader" "Skipping $streamer - sponsored content" -t 3000 -u low
    return
  fi

  DURATION=$(yt-dlp --get-duration "$VOD_URL" 2>/dev/null || echo "Unknown Duration")
  NOTIFY_ID=$(($(echo "$VOD_ID" | cksum | cut -f1 -d' ') % 2147483647))

  notify-send -r $NOTIFY_ID "📥 Downloading" "$VOD_TITLE [$DURATION]" -t 2000 -u normal
  write_status "⬇️ $streamer (0MB)" "$VOD_TITLE [$DURATION]"

  OUTPUT_PATH="$TWITCH_VOD_DIR/%(title)s-${VOD_ID}.mp4"

  # Streamlink execution (Fixed the backslash/space bugs)
  if [ -n "$TWITCH_TOKEN" ]; then
    streamlink \
      --twitch-disable-ads \
      --twitch-api-header "Authorization=OAuth $TWITCH_TOKEN" \
      --force \
      --stream-segment-threads 2 \
      --output "$OUTPUT_PATH" \
      "$VOD_URL" best >/dev/null 2>&1 &
  else
    streamlink \
      --twitch-disable-ads \
      --force \
      --stream-segment-threads 8 \
      --output "$OUTPUT_PATH" \
      "$VOD_URL" best >/dev/null 2>&1 &
  fi

  DOWNLOAD_PID=$!
  sleep 3

  # Find the file (using VOD_ID as the anchor)
  FILENAME=$(find "$TWITCH_VOD_DIR" -type f -name "*${VOD_ID}*" 2>/dev/null | head -n 1)

  while kill -0 $DOWNLOAD_PID 2>/dev/null; do
    sleep 2
    if [ -n "$FILENAME" ] && [ -f "$FILENAME" ]; then
      CURRENT_SIZE=$(stat -c%s "$FILENAME" 2>/dev/null || stat -f%z "$FILENAME" 2>/dev/null)
      SIZE_MB=$(awk "BEGIN {printf \"%.0f\", $CURRENT_SIZE / 1024 / 1024}")
      if [ "$SIZE_MB" -gt 1000 ]; then
        SIZE_GB=$(awk "BEGIN {printf \"%.1f\", $CURRENT_SIZE / 1024 / 1024 / 1024}")
        write_status "⬇️ $streamer (${SIZE_GB}GB)" "$VOD_TITLE [$DURATION]"
      else
        write_status "⬇️ $streamer (${SIZE_MB}MB)" "$VOD_TITLE [$DURATION]"
      fi
    else
      FILENAME=$(find "$TWITCH_VOD_DIR" -type f -name "*${VOD_ID}*" 2>/dev/null | head -n 1)
    fi
  done

  wait $DOWNLOAD_PID

  if [ $? -eq 0 ]; then
    OLD_VOD_ID=$(grep "^${streamer}:" "$ARCHIVE_FILE" 2>/dev/null | cut -d: -f2)
    if [ -n "$OLD_VOD_ID" ]; then
      OLD_FILE=$(find "$TWITCH_VOD_DIR" -type f -name "*${OLD_VOD_ID}*" 2>/dev/null)
      if [ -n "$OLD_FILE" ]; then
        echo "Deleting old VOD for $streamer: $OLD_FILE"
        rm -f "$OLD_FILE"
        notify-send "Twitch VOD Downloader" "Deleted old VOD for $streamer" -t 3000 -u low
      fi
    fi

    grep -v "^${streamer}:" "$ARCHIVE_FILE" >"${ARCHIVE_FILE}.tmp" 2>/dev/null || true
    echo "${streamer}:${VOD_ID}" >>"${ARCHIVE_FILE}.tmp"
    mv "${ARCHIVE_FILE}.tmp" "$ARCHIVE_FILE"

    write_status "✅ $streamer" "$VOD_TITLE (Download Complete)"
    sleep 5
    notify-send -r $NOTIFY_ID "✓ Download Complete" "$VOD_TITLE" -t 5000 -u normal
  else
    write_status "❌ $streamer" "$VOD_TITLE (Download Failed)"
    sleep 5
    notify-send -r $NOTIFY_ID "✗ Download Failed" "$VOD_TITLE" -t 5000 -u critical
  fi
}

# ==============================================================================
# MAIN EXECUTION LOOP
# ==============================================================================

mkdir -p "$TWITCH_VOD_DIR"
touch "$ARCHIVE_FILE"

write_status "⬇️ Twitch" "Starting VOD check for ${#STREAMERS[@]} streamers."

for STREAMER in "${STREAMERS[@]}"; do
  echo "Checking for new VODs from $STREAMER..."
  download_vods "$STREAMER"
done

echo "VOD download check complete!"
