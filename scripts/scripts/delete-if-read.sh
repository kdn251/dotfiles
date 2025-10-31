#!/bin/bash

VIDEO_DIR="$HOME/Videos/newsboat"
URL="$1"

# Extract video ID from URL
VIDEO_ID=$(echo "$URL" | grep -oP '[a-zA-Z0-9_-]{11}' | head -n 1)

if [ -n "$VIDEO_ID" ]; then
  # Find and delete the video file
  DELETED_FILE=$(find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null)

  if [ -n "$DELETED_FILE" ]; then
    rm -f "$DELETED_FILE"
    notify-send "Deleted Downloaded Video" "Removed: $(basename "$DELETED_FILE")" -t 3000

    # Update the downloaded query
    ~/scripts/update-downloaded-query.sh
  fi
fi
