#!/bin/bash

# --- CONFIGURATION ---
BASE_VIDEO_DIR="$HOME/Videos/newsboat"
TWITCH_VOD_DIR="$BASE_VIDEO_DIR/twitch-vods"
ARCHIVE_FILE="$BASE_VIDEO_DIR/.downloaded-twitch-vods"
TWITCH_TOKEN=$(cat ~/.newsboat/.twitch_oauth 2>/dev/null)
WAYBAR_STATUS_FILE="/tmp/twitch_vod_status.txt"

# Ensure directories exist
mkdir -p "$TWITCH_VOD_DIR"
touch "$ARCHIVE_FILE"

# Capture Newsboat Arguments
URL="$1"
TITLE="$2"

# --- NEW: Extract Streamer Name ---
# Initial attempt: pull from URL
STREAMER=$(echo "$URL" | sed -E 's|.*twitch.tv/([^/]+).*|\1|')

# If the URL is a direct /videos/ link, the streamer name will be "videos"
# In that case, we ask yt-dlp for the actual channel name (uploader)
if [ "$STREAMER" == "videos" ] || [ -z "$STREAMER" ]; then
  # --get-filename with a custom template is the fastest way to get metadata without a full download
  STREAMER=$(yt-dlp --get-filename -o "%(uploader)s" "$URL" 2>/dev/null)
  # Final fallback if yt-dlp fails
  [ -z "$STREAMER" ] && STREAMER="Twitch"
fi

# 1. Extract VOD ID
VOD_ID=$(echo "$URL" | grep -oP '(\d{9,12})' | head -n 1)
[ -z "$VOD_ID" ] && VOD_ID=$(echo "$URL" | cksum | cut -f1 -d' ')

# 2. Check Archive
if grep -q "$VOD_ID" "$ARCHIVE_FILE"; then
  notify-send "Twitch Downloader" "VOD already downloaded/archived." -t 3000
  exit 0
fi

# 3. Setup Notifications
NOTIFY_ID=$(($(echo "$VOD_ID" | cksum | cut -f1 -d' ') % 2147483647))
notify-send -r "$NOTIFY_ID" "📥 Starting Download" "[$STREAMER] $TITLE" -t 3000

# 4. Define Output Path (NOW WITH RESTRICTED FILENAMES)
# --restrict-filenames ensures no spaces or weird characters break our delete script
# We use [%(id)s] to make the ID a unique, easy-to-find 'anchor'
OUTPUT_TEMPLATE="%(title)s [%(id)s].%(ext)s"

# 5. Start Download (Optimized for 2.8K Screen + MP4)
if [[ "$URL" == *"youtube.com"* ]] || [[ "$URL" == *"youtu.be"* ]]; then
  # --merge-output-format mp4 forces the final file to be an MP4
  yt-dlp -f "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440][ext=mp4]/best" \
    --merge-output-format mp4 \
    --restrict-filenames \
    -o "$TWITCH_VOD_DIR/%(title)s [%(id)s].%(ext)s" \
    "$URL" >/dev/null 2>&1 &
else
  # Twitch logic remains the same...
  SAFE_NAME=$(yt-dlp --get-filename --restrict-filenames -o "%(title)s [%(id)s].%(ext)s" "$URL" 2>/dev/null)
  OUTPUT_PATH="$TWITCH_VOD_DIR/$SAFE_NAME"

  streamlink "${STREAMLINK_OPTS[@]}" --output "$OUTPUT_PATH" "$URL" "1080p60,best" >/dev/null 2>&1 &
fi
DOWNLOAD_PID=$!

# --- BEFORE THE LOOP: Ensure STREAMER is set for YouTube ---
if [[ "$URL" == *"youtube.com"* ]] || [[ "$URL" == *"youtu.be"* ]]; then
  # If it's YouTube and STREAMER is empty or "Manual", get the Channel Name
  if [ "$STREAMER" == "Manual" ] || [ -z "$STREAMER" ]; then
    STREAMER=$(yt-dlp --get-filename -o "%(uploader)s" "$URL" 2>/dev/null)
    [ -z "$STREAMER" ] && STREAMER="YouTube"
  fi
fi

# --- THE MONITOR LOOP ---
while kill -0 $DOWNLOAD_PID 2>/dev/null; do
  sleep 3
  # Note: yt-dlp often downloads to a .part file first.
  # We check for the final path OR the .part version to keep Waybar updated.
  TEMP_FILE="${OUTPUT_PATH}.part"
  TARGET_FILE="$OUTPUT_PATH"

  if [ -f "$TARGET_FILE" ]; then
    FILE_TO_STAT="$TARGET_FILE"
  elif [ -f "$TEMP_FILE" ]; then
    FILE_TO_STAT="$TEMP_FILE"
  else
    continue
  fi

  CURRENT_SIZE=$(stat -c%s "$FILE_TO_STAT" 2>/dev/null)
  SIZE_MB=$((CURRENT_SIZE / 1024 / 1024))

  if [ "$SIZE_MB" -gt 1024 ]; then
    SIZE_GB=$(awk "BEGIN {printf \"%.1f\", $CURRENT_SIZE / 1024 / 1024 / 1024}")
    printf "  %s (%sGB)\n%s" "$STREAMER" "$SIZE_GB" "$TITLE" >"$WAYBAR_STATUS_FILE"
  else
    printf "  %s (%sMB)\n%s" "$STREAMER" "$SIZE_MB" "$TITLE" >"$WAYBAR_STATUS_FILE"
  fi
done

# 7. Finalize
wait $DOWNLOAD_PID
if [ $? -eq 0 ]; then
  echo "$VOD_ID" >>"$ARCHIVE_FILE"
  printf "  %s (Done)\n%s" "$STREAMER" "$TITLE" >"$WAYBAR_STATUS_FILE"
  notify-send -r "$NOTIFY_ID" "✓ Download Complete" "[$STREAMER] $TITLE" -t 5000
  sleep 5
  echo " " >"$WAYBAR_STATUS_FILE"
else
  printf "  %s (Failed)\n%s" "$STREAMER" "$TITLE" >"$WAYBAR_STATUS_FILE"
  notify-send -r "$NOTIFY_ID" "✗ Download Failed" "[$STREAMER] $TITLE" -t 5000 -u critical
fi
