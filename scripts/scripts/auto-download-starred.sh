#!/bin/bash

# ==============================================================================
# CONFIGURATION
# ==============================================================================
source "$HOME/.newsboat/miniflux_creds"

VIDEO_DIR="$HOME/Videos/newsboat/starred-downloads"
LOG_FILE="$HOME/.newsboat/auto-download.log"
WAYBAR_STATUS_FILE="/tmp/miniflux_download_status.txt"
# ------------------------------------------------------------------------------

# ==============================================================================
# FUNCTIONS
# ==============================================================================

# Function to write the 'hidden' state (single space)
hide_module() {
  # Writing a single space is the standard way to hide the module when
  # 'hide-empty-text: true' is set in Waybar config.
  echo " " >"$WAYBAR_STATUS_FILE"
}

# Function to clean up on exit (critical for clearing Waybar status)
cleanup() {
  hide_module
  echo "$(date): Script terminated. Waybar status cleared." >>"$LOG_FILE"
}

# Trap signals (EXIT, Ctrl+C, kill) for robust cleanup
# The EXIT trap will call cleanup at the end of the script regardless of how it exits.
trap cleanup EXIT SIGINT SIGTERM

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

# Ensure the status file is hidden initially
hide_module

# 1. Setup
mkdir -p "$VIDEO_DIR"
echo "🔎" >"$WAYBAR_STATUS_FILE" # Briefly show 'searching' icon

# 2. Get Starred Data
STARRED_DATA=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
  "${MINIFLUX_URL}/v1/entries?starred=true&limit=1000" |
  jq -r '.entries[] | select(.url | test("youtube\\.com/watch|youtu\\.be/")) | "\(.url)||\(.title)"')

# Check if curl failed to fetch data
if [ $? -ne 0 ]; then
  echo "❌ ERROR" >"$WAYBAR_STATUS_FILE"
  sleep 5
  exit 1 # EXIT trap will run cleanup
fi

TOTAL=$(echo "$STARRED_DATA" | wc -l)
CURRENT=0
DOWNLOADED=0

echo "$(date): Starting auto-download of $TOTAL starred YouTube videos" >>"$LOG_FILE"

# Set initial Waybar status
echo "📥 $TOTAL" >"$WAYBAR_STATUS_FILE"

# 3. Download Loop
while IFS='||' read -r URL TITLE; do
  if [ -z "$URL" ]; then
    continue
  fi

  CURRENT=$((CURRENT + 1))

  # Set Waybar status to current video number (0% until download starts)
  echo "⬇️ $CURRENT(0.0%)/$TOTAL" >"$WAYBAR_STATUS_FILE"

  # Extraction (VIDEO_ID, Check already downloaded, etc. remain the same)
  VIDEO_ID=$(echo "$URL" | grep -oP '(?<=watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11}')

  if [ -z "$VIDEO_ID" ]; then
    echo "$(date): [$CURRENT/$TOTAL] Failed to extract video ID from: $URL" >>"$LOG_FILE"
    echo "❌ $CURRENT/$TOTAL (ID Error)" >"$WAYBAR_STATUS_FILE"
    sleep 1
    continue
  fi

  # Check if already downloaded
  if find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null | grep -q .; then
    echo "$(date): [$CURRENT/$TOTAL] Already downloaded: $VIDEO_ID - $TITLE" >>"$LOG_FILE"
    echo "⏭️ $CURRENT/$TOTAL" >"$WAYBAR_STATUS_FILE"
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
      # Update Waybar with video number and current percentage
      echo "⬇️ $CURRENT($PERCENT%)/$TOTAL" >"$WAYBAR_STATUS_FILE"
    fi
  done

  # Check if download succeeded (and update final count/status)
  if find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null | grep -q .; then
    DOWNLOADED=$((DOWNLOADED + 1))
    echo "$(date): [$CURRENT/$TOTAL] ✓ Success: $TITLE" >>"$LOG_FILE"
    # Ensure Waybar briefly shows 100% completion
    echo "✅ $CURRENT(100%)/$TOTAL" >"$WAYBAR_STATUS_FILE"
  else
    echo "$(date): [$CURRENT/$TOTAL] ✗ Failed: $TITLE" >>"$LOG_FILE"
    echo "❌ $CURRENT/$TOTAL (Download Failed)" >"$WAYBAR_STATUS_FILE"
  fi

  # Small delay to be nice to YouTube
  sleep 2

done < <(echo "$STARRED_DATA")

# 4. Finalization
~/scripts/update-downloaded-query.sh

echo "$(date): Auto-download complete - Downloaded: $DOWNLOADED/$TOTAL" >>"$LOG_FILE"

# Final Waybar Status (Show result briefly)
echo "✅ $DOWNLOADED/$TOTAL DONE" >"$WAYBAR_STATUS_FILE"
sleep 5 # Keep final status visible for 5 seconds

# Final notification (not persistent)
notify-send "📥 Auto-Download Complete" "Downloaded $DOWNLOADED out of $TOTAL videos\n\nCheck log for details." -t 5000

# The EXIT trap will now call cleanup() and hide the module after the 5 second sleep.
