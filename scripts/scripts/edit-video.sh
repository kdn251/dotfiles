#!/bin/bash

# Define the directory
REC_DIR="$HOME/Videos/Recordings"

# Find the most recent files
SCREEN_FILE=$(ls -t "$REC_DIR"/*screen* 2>/dev/null | head -n 1)
WEBCAM_FILE=$(ls -t "$REC_DIR"/*webcam* 2>/dev/null | head -n 1)

# Generate a logical name: YYYY-MM-DD_HHMM-edited.mp4
TIMESTAMP=$(date +"%Y-%m-%d_%H%M")
OUTPUT_FILE="$REC_DIR/${TIMESTAMP}-edited.mp4"

# Check if both files were found
if [ -z "$SCREEN_FILE" ] || [ -z "$WEBCAM_FILE" ]; then
  dunstify -u critical "FFmpeg Error" "Could not find recording files in $REC_DIR"
  exit 1
fi

# 1. Show Dunst notification
dunstify -u normal "FFmpeg Processing" "Creating $TIMESTAMP-edited.mp4..."

# Execute FFmpeg
ffmpeg -y -i "$SCREEN_FILE" -i "$WEBCAM_FILE" -filter_complex \
  "[1:v]scale=480:-1[wm]; [0:v][wm]overlay=W-w-10:H-h-10[outv]" \
  -map "[outv]" -map 1:a -c:v libx264 -crf 23 -preset veryfast -c:a copy "$OUTPUT_FILE"

# Check if FFmpeg succeeded
if [ $? -eq 0 ]; then
  dunstify -u normal "FFmpeg Success" "Video saved as $(basename "$OUTPUT_FILE")"

  # 2. Open the edited file with mpv
  mpv "$OUTPUT_FILE"
else
  dunstify -u critical "FFmpeg Error" "The rendering process failed."
fi
