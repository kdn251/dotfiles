#!/bin/bash

VIDEO_DIR="$HOME/Videos/newsboat"
URL="$1"

# Extract video ID from URL
VIDEO_ID=$(echo "$URL" | grep -oP '[a-zA-Z0-9_-]{11}' | head -n 1)

if [ -n "$VIDEO_ID" ]; then
  # Find files
  DELETED_FILES=$(find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null)

  if [ -n "$DELETED_FILES" ]; then
    # Delete each file
    echo "$DELETED_FILES" | while read file; do
      rm -f "$file"
    done

    notify-send "Deleted Video" "Removed from downloads" -t 3000

    # Update the downloaded query
    ~/scripts/update-downloaded-query.sh
  else
    notify-send "Not Downloaded" "Video not found locally" -t 3000
  fi
else
  notify-send "Error" "Could not extract video ID" -t 3000
fi
