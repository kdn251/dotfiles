#!/bin/bash

VIDEO_DIR="$HOME/Videos/newsboat"
URL="$1"
VIDEO_ID=$(echo "$URL" | grep -oP '[a-zA-Z0-9_-]{11}' | head -n 1)

# Twitch VOD (numeric ID)
if [ -z "$VIDEO_ID" ]; then
  VIDEO_ID=$(echo "$URL" | grep -oP 'videos?/(\d+)' | grep -oP '\d+')
fi

if [ -n "$VIDEO_ID" ]; then
  # Kill any yt-dlp process downloading this video ID
  if pkill -f "yt-dlp.*$VIDEO_ID"; then

    # List files before delete
    find "$VIDEO_DIR" -name "*${VIDEO_ID}*" -type f >>/tmp/cancel-debug.log

    # Remove ALL files related to this video ID
    find "$VIDEO_DIR" -name "*${VIDEO_ID}*" -type f -delete

    notify-send "Download Cancelled" "Stopped download and cleaned up files" -t 3000
  else
    notify-send "Not Downloading" "No active download found" -t 3000
  fi
else
  notify-send "Error" "Could not extract video ID" -t 3000
fi
