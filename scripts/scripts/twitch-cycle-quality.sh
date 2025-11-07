#!/bin/bash
# ~/scripts/twitch-cycle-quality.sh

CONTEXT_FILE="/tmp/twitch-stream-context.conf"
QUALITY_FILE="/tmp/twitch-current-quality.txt"

# --- A. Load Context and Current Quality ---
# Load stream URL, username, and token path from the context file
if [ -f "$CONTEXT_FILE" ]; then
  source "$CONTEXT_FILE"
else
  notify-send "Twitch Error" "No active stream context found to cycle quality." -t 5000 -u critical
  exit 1
fi

# Define the cycle of qualities
QUALITIES=("best" "720p60" "480p" "360p")
DEFAULT_QUALITY="best"

# Get current quality or default
CURRENT_QUALITY=$(cat "$QUALITY_FILE" 2>/dev/null || echo "$DEFAULT_QUALITY")

# --- B. Cycle Quality Logic ---
NEXT_QUALITY=""
FOUND=0

for i in "${!QUALITIES[@]}"; do
  if [ "${QUALITIES[$i]}" == "$CURRENT_QUALITY" ]; then
    NEXT_INDEX=$((i + 1))
    # Loop back to the start
    if [ "$NEXT_INDEX" -ge "${#QUALITIES[@]}" ]; then
      NEXT_INDEX=0
    fi
    NEXT_QUALITY="${QUALITIES[$NEXT_INDEX]}"
    FOUND=1
    break
  fi
done

# Fallback
if [ "$FOUND" -eq 0 ]; then
  NEXT_QUALITY="${QUALITIES[0]}"
fi

# Write the new quality for the next cycle
echo "$NEXT_QUALITY" >"$QUALITY_FILE"

# --- C. Kill and Relaunch ---

notify-send "Twitch Quality" "Switching to **$NEXT_QUALITY**..." -t 3000

# 1. Kill the existing streamlink/mpv process
# Note: Killing by '--player' argument is safest as it only kills the stream process.
pkill -f "streamlink.*--player" 2>/dev/null
echo "INFO: Killed existing streamlink process for relaunch." >>/tmp/twitch-stream-debug.log

# 2. Relaunch the stream with the new quality

# Read OAuth token (in case the file changed)
TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)

if [ -n "$TWITCH_TOKEN" ]; then
  streamlink \
    --twitch-low-latency \
    --twitch-disable-ads \
    --twitch-api-header "Authorization=OAuth $TWITCH_TOKEN" \
    --player mpv \
    --player-args "--cache=yes --force-window=immediate" \
    --stream-segment-threads 3 \
    --stream-segment-attempts 3 \
    --stream-segment-timeout 10 \
    --retry-streams 2 \
    --retry-open 2 \
    "$URL" "$NEXT_QUALITY" >/dev/null 2>&1 & # Use NEXT_QUALITY and fork!
else
  streamlink \
    --twitch-low-latency \
    --twitch-disable-ads \
    --player mpv \
    --player-args "--cache=yes --force-window=immediate" \
    "$URL" "$NEXT_QUALITY" >/dev/null 2>&1 & # Use NEXT_QUALITY and fork!
fi

echo "INFO: Relaunched $STREAMER_USERNAME at quality $NEXT_QUALITY." >>/tmp/twitch-stream-debug.log
