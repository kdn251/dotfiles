#!/bin/bash

VIDEO_DIR="$HOME/Videos/newsboat"
URL="$1"

# 1. Extract the ID
VIDEO_ID=$(echo "$URL" | grep -oP '(\d{9,12}|[a-zA-Z0-9_-]{11})' | head -n 1)

if [ -n "$VIDEO_ID" ]; then
  # 2. Search for the ID inside brackets [ID]
  # This is the 'anchor' we just added to the downloader
  DELETED_FILES=$(find "$VIDEO_DIR" -type f -name "*[${VIDEO_ID}]*" 2>/dev/null)

  if [ -n "$DELETED_FILES" ]; then
    echo "$DELETED_FILES" | while read -r file; do
      rm -f "$file"
    done
    notify-send "🗑️ Video Deleted" "Removed: $VIDEO_ID" -t 3000

    # Cleanup Twitch archive & Newsboat query
    sed -i "/$VIDEO_ID/d" "$VIDEO_DIR/.downloaded-twitch-vods" 2>/dev/null
    ~/scripts/update-downloaded-query.sh 2>/dev/null
  else
    notify-send "Not Found" "No file found with ID [${VIDEO_ID}]" -t 3000 -u low
  fi
else
  notify-send "Error" "Could not extract ID from URL" -t 3000 -u critical
fi
