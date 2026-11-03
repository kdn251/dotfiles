#!/bin/bash

# Define the directory
REC_DIR="$HOME/Videos/Recordings"

# Pick the newest screen recording, then require its exact session partner.
# Never substitute an older webcam recording when capture failed.
SCREEN_FILE=""
shopt -s nullglob
for candidate in "$REC_DIR"/recording_*.screen.mp4; do
  if [ -f "$candidate" ] && { [ -z "$SCREEN_FILE" ] || [ "$candidate" -nt "$SCREEN_FILE" ]; }; then
    SCREEN_FILE="$candidate"
  fi
done

if [ -z "$SCREEN_FILE" ]; then
  dunstify -u critical "FFmpeg Error" "No screen recording found in $REC_DIR"
  exit 1
fi

WEBCAM_FILE="${SCREEN_FILE%.screen.mp4}.webcam.mkv"
if [ ! -s "$WEBCAM_FILE" ]; then
  dunstify -u critical "FFmpeg Error" "Missing webcam recording for $(basename "$SCREEN_FILE"). Record a new screen and webcam session together."
  exit 1
fi

# Generate a logical name: YYYY-MM-DD_HHMM-edited.mp4
TIMESTAMP=$(date +"%Y-%m-%d_%H%M")
OUTPUT_FILE="$REC_DIR/${TIMESTAMP}-edited.mp4"

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
