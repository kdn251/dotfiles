#!/bin/bash
VIDEO_DIR="$HOME/Videos/newsboat"
ARCHIVE_FILE="$VIDEO_DIR/.downloaded-twitch-vods"
TWITCH_TOKEN=$(cat ~/.newsboat/.twitch_oauth 2>/dev/null)

# Create directory structure
mkdir -p "$VIDEO_DIR"
touch "$ARCHIVE_FILE"

# List of streamers to download from (add your favorites)
STREAMERS=(
  "samwitch"
  "xqc"
  "zackrawrr"
  "shroud"
)

# Function to get VOD list and download
download_vods() {
  local streamer=$1

  notify-send "Twitch VOD Downloader" "Checking $streamer for new VODs..." -t 3000 -u low

  # Get only the most recent VOD (--playlist-end 1)
  VOD_URL=$(yt-dlp --flat-playlist --print url --playlist-end 1 "https://www.twitch.tv/$streamer/videos" 2>/dev/null)

  [ -z "$VOD_URL" ] && return

  # Extract VOD ID
  VOD_ID=$(echo "$VOD_URL" | grep -oP 'videos/\K[0-9]+')

  # Check if this specific VOD is already downloaded
  EXISTING=$(find "$VIDEO_DIR" -type f -name "*${VOD_ID}*" 2>/dev/null | head -n 1)
  if [ -n "$EXISTING" ]; then
    echo "Most recent VOD already downloaded: $VOD_ID"
    return
  fi

  # Get VOD title and duration for notifications
  VOD_TITLE=$(yt-dlp --get-title "$VOD_URL" 2>/dev/null || echo "Unknown")
  DURATION=$(yt-dlp --get-duration "$VOD_URL" 2>/dev/null || echo "Unknown")

  # Convert VOD ID to numeric notification ID
  NOTIFY_ID=$(($(echo "$VOD_ID" | cksum | cut -f1 -d' ') % 2147483647))

  notify-send -r $NOTIFY_ID "📥 Downloading" "$VOD_TITLE [$DURATION]" -t 2000 -u normal

  # Start download in background
  if [ -n "$TWITCH_TOKEN" ]; then
    streamlink \
      --twitch-disable-ads \
      --twitch-api-header "Authorization=OAuth $TWITCH_TOKEN" \
      --force \
      --stream-segment-threads 8 \
      --output "$VIDEO_DIR/{title}-${VOD_ID}.mp4" \
      "$VOD_URL" best >/dev/null 2>&1 &
  else
    streamlink \
      --twitch-disable-ads \
      --force \
      --stream-segment-threads 8 \
      --output "$VIDEO_DIR/{title}-${VOD_ID}.mp4" \
      "$VOD_URL" best >/dev/null 2>&1 &
  fi

  DOWNLOAD_PID=$!

  # Monitor file size and show progress in MB/GB
  # Wait a moment for file to be created
  sleep 3
  FILENAME=$(find "$VIDEO_DIR" -type f -name "*${VOD_ID}*" 2>/dev/null | head -n 1)

  while kill -0 $DOWNLOAD_PID 2>/dev/null; do
    sleep 2
    if [ -n "$FILENAME" ] && [ -f "$FILENAME" ]; then
      CURRENT_SIZE=$(stat -c%s "$FILENAME" 2>/dev/null || stat -f%z "$FILENAME" 2>/dev/null)

      # Show size in MB or GB
      SIZE_MB=$(awk "BEGIN {printf \"%.0f\", $CURRENT_SIZE / 1024 / 1024}")
      if [ "$SIZE_MB" -gt 1000 ]; then
        SIZE_GB=$(awk "BEGIN {printf \"%.1f\", $CURRENT_SIZE / 1024 / 1024 / 1024}")
        notify-send -r $NOTIFY_ID -t 0 -u low "📥 ${SIZE_GB}GB [$DURATION]" "$VOD_TITLE"
      else
        notify-send -r $NOTIFY_ID -t 0 -u low "📥 ${SIZE_MB}MB [$DURATION]" "$VOD_TITLE"
      fi
    else
      # Try to find the file again
      FILENAME=$(find "$VIDEO_DIR" -type f -name "*${VOD_ID}*" 2>/dev/null | head -n 1)
    fi
  done

  # Wait for download to complete
  wait $DOWNLOAD_PID

  # Check if download succeeded
  if [ $? -eq 0 ]; then
    # Download successful - now delete old VODs for THIS streamer only
    # Get the old VOD ID for this streamer from archive
    OLD_VOD_ID=$(grep "^${streamer}:" "$ARCHIVE_FILE" 2>/dev/null | cut -d: -f2)

    if [ -n "$OLD_VOD_ID" ]; then
      OLD_FILE=$(find "$VIDEO_DIR" -type f -name "*${OLD_VOD_ID}*" 2>/dev/null)
      if [ -n "$OLD_FILE" ]; then
        echo "Deleting old VOD for $streamer: $OLD_FILE"
        rm -f "$OLD_FILE"
        notify-send "Twitch VOD Downloader" "Deleted old VOD for $streamer" -t 3000 -u low
      fi
    fi

    # Update archive: remove old entry for this streamer and add new one
    grep -v "^${streamer}:" "$ARCHIVE_FILE" >"${ARCHIVE_FILE}.tmp" 2>/dev/null || true
    echo "${streamer}:${VOD_ID}" >>"${ARCHIVE_FILE}.tmp"
    mv "${ARCHIVE_FILE}.tmp" "$ARCHIVE_FILE"

    notify-send -r $NOTIFY_ID "✓ Download Complete" "$VOD_TITLE" -t 5000 -u normal
  else
    notify-send -r $NOTIFY_ID "✗ Download Failed" "$VOD_TITLE" -t 5000 -u critical
  fi
}

for STREAMER in "${STREAMERS[@]}"; do
  echo "Checking for new VODs from $STREAMER..."
  download_vods "$STREAMER"
done

notify-send "Twitch VOD Downloader" "All downloads complete!" -t 3000 -u low
echo "VOD download check complete!"
