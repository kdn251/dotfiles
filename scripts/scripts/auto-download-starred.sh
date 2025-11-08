#!/bin/bash

# ==============================================================================
# CONFIGURATION
# ==============================================================================
source "$HOME/.newsboat/miniflux_creds"

VIDEO_DIR="$HOME/Videos/newsboat/starred-downloads"
LOG_FILE="$HOME/.newsboat/auto-download.log"
WAYBAR_STATUS_FILE="/tmp/miniflux_download_status.txt"

# ==============================================================================
# FUNCTIONS
# ==============================================================================

# Function to clean up on exit (critical for clearing Waybar status)
cleanup() {
  # Write an empty JSON object to clear the module text
  echo "{}" >"$WAYBAR_STATUS_FILE"
  echo "$(date): Script terminated. Waybar status cleared." >>"$LOG_FILE"
}

# Helper function to create the JSON output
# Arguments: $1 = main_text, $2 = tooltip_text
write_waybar_json() {
  # Escape any double quotes in the text/tooltip to prevent breaking the JSON structure
  local main_text=$(echo "$1" | sed 's/"/\\"/g')
  local tooltip_text=$(echo "$2" | sed 's/"/\\"/g')

  echo "{\"text\":\"$main_text\", \"tooltip\":\"$tooltip_text\"}" >"$WAYBAR_STATUS_FILE"
}

# Trap signals (EXIT, Ctrl+C, kill) for robust cleanup
trap cleanup EXIT SIGINT SIGTERM

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

# 1. Setup
mkdir -p "$VIDEO_DIR"
# Initial clear using JSON format
write_waybar_json "" "Initializing..."

# 2. Get Starred Data
STARRED_DATA=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
  "${MINIFLUX_URL}/v1/entries?starred=true&limit=1000" |
  jq -r '.entries[] | select(.url | test("youtube\\.com/watch|youtu\\.be/")) | "\(.url)||\(.title)"')

TOTAL=$(echo "$STARRED_DATA" | wc -l)
CURRENT=0
DOWNLOADED=0

echo "$(date): Starting auto-download of $TOTAL starred YouTube videos" >>"$LOG_FILE"

# Set initial Waybar status
write_waybar_json "📥 $TOTAL" "Starting download of $TOTAL videos"

# 3. Download Loop (using process substitution for outer loop)
while IFS='||' read -r URL TITLE; do
  if [ -z "$URL" ]; then
    continue
  fi

  CURRENT=$((CURRENT + 1))

  # Set Waybar status to current video number (0% until download starts)
  write_waybar_json "⬇️ $CURRENT(0.0%)/$TOTAL" "Initializing: $TITLE"

  VIDEO_ID=$(echo "$URL" | grep -oP '(?<=watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11}')

  if [ -z "$VIDEO_ID" ]; then
    echo "$(date): [$CURRENT/$TOTAL] Failed to extract video ID from: $URL" >>"$LOG_FILE"
    continue
  fi

  # Check if already downloaded
  if find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null | grep -q .; then
    echo "$(date): [$CURRENT/$TOTAL] Already downloaded: $VIDEO_ID - $TITLE" >>"$LOG_FILE"
    write_waybar_json "⏭️ $CURRENT/$TOTAL" "Skipping (Already Downloaded): $TITLE"
    sleep 1
    continue
  fi

  echo "$(date): [$CURRENT/$TOTAL] Downloading: $TITLE" >>"$LOG_FILE"

  # Download with yt-dlp and monitor progress in a nested loop
  yt-dlp -f 'best[height<=?1080]' \
    -o "$VIDEO_DIR/%(title)s-%(id)s.%(ext)s" \
    --concurrent-fragments 8 \
    --newline \
    "$URL" 2>&1 | while read line; do
    if [[ "$line" =~ ([0-9]+\.[0-9]+)% ]]; then
      PERCENT="${BASH_REMATCH[1]}"
      # Update Waybar with video number and current percentage in JSON format
      write_waybar_json "⬇️ $CURRENT($PERCENT%)/$TOTAL" "$TITLE"
    fi
  done

  # Check if download succeeded (and update final count/status)
  if find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null | grep -q .; then
    DOWNLOADED=$((DOWNLOADED + 1))
    echo "$(date): [$CURRENT/$TOTAL] ✓ Success: $TITLE" >>"$LOG_FILE"
    # Ensure Waybar briefly shows 100% completion before moving to next item
    write_waybar_json "✅ $CURRENT(100%)/$TOTAL" "Downloaded: $TITLE"
  else
    echo "$(date): [$CURRENT/$TOTAL] ✗ Failed: $TITLE" >>"$LOG_FILE"
    write_waybar_json "❌ $CURRENT/$TOTAL" "Failed: $TITLE"
  fi

  # Small delay to be nice to YouTube
  sleep 2

done < <(echo "$STARRED_DATA")

# 4. Finalization
~/scripts/update-downloaded-query.sh

echo "$(date): Auto-download complete - Downloaded: $DOWNLOADED/$TOTAL" >>"$LOG_FILE"

# Final Waybar Status (Show result briefly)
write_waybar_json "✅ $DOWNLOADED/$TOTAL" "All downloads complete."
sleep 5

# Final notification (not persistent) - THIS IS THE ONLY ONE KEPT
notify-send "📥 Auto-Download Complete" "Downloaded $DOWNLOADED out of $TOTAL videos\n\nCheck log for details." -t 5000
