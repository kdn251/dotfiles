#!/bin/bash
CLIP_DIR="$HOME/Videos/clips"
CLIP_LENGTH=30
mkdir -p "$CLIP_DIR"

# Try YouTube socket first, then Twitch
if [ -S "/tmp/mpv-yt-ipc" ]; then
  SOCKET="/tmp/mpv-yt-ipc"
elif [ -S "/tmp/mpv-twitch-ipc" ]; then
  SOCKET="/tmp/mpv-twitch-ipc"
else
  notify-send "Clip" "No active mpv instance"
  exit 1
fi

# Get current position and file path from mpv
POS=$(echo '{"command": ["get_property", "time-pos"]}' | socat - "$SOCKET" 2>/dev/null | jq '.data')
FILEPATH=$(echo '{"command": ["get_property", "path"]}' | socat - "$SOCKET" 2>/dev/null | jq -r '.data')
TITLE=$(echo '{"command": ["get_property", "media-title"]}' | socat - "$SOCKET" 2>/dev/null | jq -r '.data')

if [ -z "$POS" ] || [ "$POS" == "null" ]; then
  notify-send "Clip" "Could not get playback position"
  exit 1
fi

# Calculate start time (30 seconds before current position)
START=$(awk "BEGIN {v=$POS-$CLIP_LENGTH; if(v<0) v=0; printf \"%.0f\", v}")

# Clean filename
SAFE_TITLE=$(echo "$TITLE" | tr -dc '[:alnum:] _-' | head -c 50)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT="$CLIP_DIR/${SAFE_TITLE}_${TIMESTAMP}.mp4"

notify-send "Clip" "Saving last ${CLIP_LENGTH}s..." -t 2000

# Download and clip the segment
yt-dlp --cookies-from-browser firefox \
  --download-sections "*${START}-${POS}" \
  -o "$OUTPUT" \
  "$FILEPATH" 2>/dev/null

if [ $? -eq 0 ]; then
  notify-send -i "$OUTPUT" "Clip" "Saved: $(basename "$OUTPUT")"
else
  notify-send "Clip" "Failed to save clip"
fi
