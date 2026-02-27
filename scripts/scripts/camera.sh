#!/bin/bash

WINDOW_TITLE="Webcam_Floating_Window"

# Find the PID to toggle off if already running
PID=$(pgrep -f "mpv --no-audio --title=$WINDOW_TITLE")

if [ -n "$PID" ]; then
  echo "Webcam running (PID: $PID). Killing process..."
  kill "$PID"
  exit 0
fi

# 1. Try to find the MX Brio (Logitech) first
# We grab the first /dev/videoX path listed under 'MX Brio'
DEVICE=$(v4l2-ctl --list-devices | grep -A 1 "MX Brio" | grep -o '/dev/video[0-9]\+' | head -n 1)

# 2. Fallback to Laptop Webcam if MX Brio isn't connected
if [ -z "$DEVICE" ]; then
  echo "MX Brio not found. Searching for Laptop Webcam..."
  DEVICE=$(v4l2-ctl --list-devices | grep -A 1 "Laptop Webcam" | grep -o '/dev/video[0-9]\+' | head -n 1)
fi

# 3. Final check
if [ -z "$DEVICE" ]; then
  echo "Error: No cameras found."
  # Optional: send a notification if you have libnotify installed
  # notify-send "Camera Error" "No webcam detected"
  exit 1
fi

echo "Launching mpv on $DEVICE..."

# Launch with the v4l2 prefix for reliability
mpv \
  --no-audio \
  --title="$WINDOW_TITLE" \
  --input-vo-keyboard=no \
  --autofit=30% \
  "av://v4l2:$DEVICE" &
