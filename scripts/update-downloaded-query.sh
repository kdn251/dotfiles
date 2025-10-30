#!/bin/bash

VIDEO_DIR="$HOME/Videos/newsboat"
URLS_FILE="$HOME/.newsboat/urls"

# Get all downloaded video IDs
DOWNLOADED_IDS=$(find "$VIDEO_DIR" -type f \( -name "*.mp4" -o -name "*.webm" -o -name "*.mkv" \) |
  grep -oP '[a-zA-Z0-9_-]{11}\.(mp4|webm|mkv)' |
  sed 's/\..*//' |
  sort -u |
  tr '\n' '|' |
  sed 's/|$//')

# Remove old downloaded query if exists
sed -i '/^"query:Downloaded:/d' "$URLS_FILE"

# Add new query searching by URL
if [ -n "$DOWNLOADED_IDS" ]; then
  # echo "\"query:Downloaded:url =~ \\\"($DOWNLOADED_IDS)\\\"\" downloaded" >>"$URLS_FILE"
  # echo "\"query:Downloaded:link =~ \\\"($DOWNLOADED_IDS)\\\"\" downloaded" >>"$URLS_FILE"
  # sed -i "1i\"query:Downloaded:link =~ \\\\\"($DOWNLOADED_IDS)\\\\\"\" downloaded" "$URLS_FILE"
  sed -i "1i\"query:Downloaded:link =~ \\\\\"($DOWNLOADED_IDS)\\\\\" and feedtitle !~ \\\\\"Starred\\\\\"\" downloaded" "$URLS_FILE"
fi
