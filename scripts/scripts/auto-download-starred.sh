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

# Function to write status to the file in i3blocks format (Text\nTooltip)
# Arguments: $1 = main_text (visible on bar), $2 = tooltip_text (on hover)
write_status() {
  local main_text="$1"
  local tooltip_text="$2"

  if [ -z "$main_text" ]; then
    # If no main text, write a single space (i3blocks format with blank text)
    # This triggers 'hide-empty-text: true'
    echo " " >"$WAYBAR_STATUS_FILE"
  else
    # Write Main Text followed by a Newline and the Tooltip Text
    # Waybar will display the first line and use the second line for the tooltip.
    printf "%s\n%s" "$main_text" "$tooltip_text" >"$WAYBAR_STATUS_FILE"
  fi
}

# Function to clean up on exit (critical for clearing Waybar status)
cleanup() {
  # Hide the module by writing blank text
  write_status "" "Script finished or terminated."
  echo "$(date): Script terminated. Waybar status cleared." >>"$LOG_FILE"
}

# Trap signals (EXIT, Ctrl+C, kill) for robust cleanup
trap cleanup EXIT SIGINT SIGTERM

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

# Ensure the status file is hidden initially
write_status "" "Starting Miniflux Downloader..."

# 1. Setup
mkdir -p "$VIDEO_DIR"
write_status " " "Fetching starred videos..."

# 2. Get Starred Data
STARRED_DATA=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
  "${MINIFLUX_URL}/v1/entries?starred=true&limit=1000" |
  jq -r '.entries[] | select(.url | test("youtube\\.com/watch|youtu\\.be/")) | "\(.url)||\(.title)"')

# Check if curl failed to fetch data
if [ $? -ne 0 ]; then
  write_status "❌ ERROR" "Error fetching starred videos from Miniflux API. Check credentials/URL."
  sleep 5
  exit 1 # EXIT trap will run cleanup
fi

TOTAL=$(echo "$STARRED_DATA" | wc -l)
CURRENT=0
DOWNLOADED=0

echo "$(date): Starting auto-download of $TOTAL starred YouTube videos" >>"$LOG_FILE"

# Set initial Waybar status
write_status "📥 $TOTAL" "Starting download of $TOTAL videos"

# 3. Download Loop
while IFS='||' read -r URL TITLE; do
  if [ -z "$URL" ]; then
    continue
  fi

  CURRENT=$((CURRENT + 1))

  # Tooltip: Remove leading/trailing whitespace from TITLE
  CLEAN_TITLE=$(echo "$TITLE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

  # Set Waybar status to current video number (0% until download starts)
  write_status "⬇️ $CURRENT(0.0%)/$TOTAL" "Initializing: $CLEAN_TITLE"

  # Extraction (VIDEO_ID, Check already downloaded, etc. remain the same)
  VIDEO_ID=$(echo "$URL" | grep -oP '(?<=watch\?v=|youtu\.be/)[a-zA-Z0-9_-]{11}')

  if [ -z "$VIDEO_ID" ]; then
    echo "$(date): [$CURRENT/$TOTAL] Failed to extract video ID from: $URL" >>"$LOG_FILE"
    write_status "❌ $CURRENT/$TOTAL" "Error: Failed to extract ID from URL."
    sleep 1
    continue
  fi

  # Check if already downloaded
  if find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null | grep -q .; then
    echo "$(date): [$CURRENT/$TOTAL] Already downloaded: $VIDEO_ID - $TITLE" >>"$LOG_FILE"
    write_status "⏭️ $CURRENT/$TOTAL" "Skipping (Already Downloaded): $CLEAN_TITLE"
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
      write_status "⬇️ $CURRENT($PERCENT%)/$TOTAL" "$CLEAN_TITLE"
    fi
  done

  # Check if download succeeded (and update final count/status)
  if find "$VIDEO_DIR" -type f -name "*${VIDEO_ID}*" 2>/dev/null | grep -q .; then
    DOWNLOADED=$((DOWNLOADED + 1))
    echo "$(date): [$CURRENT/$TOTAL] ✓ Success: $TITLE" >>"$LOG_FILE"
    # Ensure Waybar briefly shows 100% completion before moving to next item
    write_status "✅ $CURRENT(100%)/$TOTAL" "Downloaded: $CLEAN_TITLE"
  else
    echo "$(date): [$CURRENT/$TOTAL] ✗ Failed: $TITLE" >>"$LOG_FILE"
    write_status "❌ $CURRENT/$TOTAL" "Failed to download: $CLEAN_TITLE"
  fi

  # Small delay to be nice to YouTube
  sleep 2

done < <(echo "$STARRED_DATA")

# 4. Finalization
~/scripts/update-downloaded-query.sh

echo "$(date): Auto-download complete - Downloaded: $DOWNLOADED/$TOTAL" >>"$LOG_FILE"

# Final Waybar Status (Show result briefly)
write_status "✅ $DOWNLOADED/$TOTAL DONE" "All downloads complete."
sleep 5 # Keep final status visible for 5 seconds

# Final notification (not persistent)
notify-send "📥 Auto-Download Complete" "Downloaded $DOWNLOADED out of $TOTAL videos\n\nCheck log for details." -t 5000

# The EXIT trap will now call cleanup() and hide the module after the 5 second sleep.
