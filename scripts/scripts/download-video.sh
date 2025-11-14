#!/bin/bash

# This script is used with newsboat to download YouTube videos

VIDEO_DIR="$HOME/Videos/newsboat/downloaded-videos"
mkdir -p "$VIDEO_DIR"

# Debug - log all arguments
echo "========== DOWNLOAD DEBUG ==========" >>/tmp/download-debug.log
echo "All args: $@" >>/tmp/download-debug.log
echo "Arg 1 (URL): $1" >>/tmp/download-debug.log
echo "Arg 2+: ${@:2}" >>/tmp/download-debug.log
date >>/tmp/download-debug.log

URL="$1"

VIDEO_ID=$(echo "$URL" | grep -oP '[a-zA-Z0-9_-]{11}' | head -n 1)
TITLE="$2"

# Get video title using yt-dlp
# TITLE=$(yt-dlp --get-title "$URL" 2>/dev/null || echo "Video")

# Check if already downloaded
if [ -n "$VIDEO_ID" ]; then
  DOWNLOADED=$(find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null | head -n 1)

  if [ -n "$DOWNLOADED" ]; then
    notify-send "Already Downloaded" "$TITLE" -t 3000 -u low

    exit 0
  fi
fi

# Get video duration
DURATION=$(yt-dlp --get-duration "$URL" 2>/dev/null || echo "Unknown")

# Show starting notification with title
notify-send "📥 Downloading" "$TITLE" -t 2000

# Download with yt-dlp, keeping video ID in filename
# yt-dlp -f 'best[height<=?1080]' \
#   -o "$VIDEO_DIR/%(title)s-%(id)s.%(ext)s" \
#   "$URL" >/dev/null 2>&1 &&
#   notify-send "✓ Download Complete" "$TITLE" -t 5000 ||
#   notify-send "✗ Download Failed" "$TITLE" -t 5000

# Download with progress in background
(
  # Convert video ID to numeric notification ID (keep it in valid range)
  NOTIFY_ID=$(($(echo "$VIDEO_ID" | cksum | cut -f1 -d' ') % 2147483647))

  # yt-dlp -f 'best[height<=?1080]' \
  #   -o "$VIDEO_DIR/%(title)s-%(id)s.%(ext)s" \
  #   --newline \
  #   "$URL" 2>&1 | while read line; do
  #   # Extract percentage from yt-dlp output
  #   if [[ "$line" =~ ([0-9]+\.[0-9]+)% ]]; then
  #     PERCENT="${BASH_REMATCH[1]}"
  #     notify-send -r $NOTIFY_ID -t 0 -u low "📥 Downloading ${PERCENT}%" "$TITLE"
  #   fi
  # done
  yt-dlp -f 'best[height<=?1080]' \
    -o "$VIDEO_DIR/%(title)s-%(id)s.%(ext)s" \
    --concurrent-fragments 8 \
    --newline \
    "$URL" 2>&1 | while read line; do
    if [[ "$line" =~ ([0-9]+\.[0-9]+)% ]]; then
      PERCENT="${BASH_REMATCH[1]}"
      # notify-send -r $NOTIFY_ID -t 0 -u low "📥 ${PERCENT}%" "$TITLE"
      notify-send -r $NOTIFY_ID -t 0 -u low "📥 ${PERCENT}% [$DURATION]" "$TITLE"
    fi
  done

  if [ ${PIPESTATUS[0]} -eq 0 ]; then
    # Update the downloaded query feed
    ~/scripts/update-downloaded-query.sh

    # Tell newsboat to reload feeds
    # pkill -USR1 newsboat

    notify-send -r $NOTIFY_ID "✓ Download Complete" "$TITLE" -t 5000
  else
    notify-send -r $NOTIFY_ID "✗ Download Failed" "$TITLE" -t 5000
  fi
) &
