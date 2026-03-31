#!/bin/bash

# 1. Path to your watch_later folder
WATCH_LATER_DIR="$HOME/.local/state/mpv/watch_later"

# 2. Find your video launcher script
# (Update this path to wherever your actual mpv/yt-dlp script lives!)
LAUNCHER="$HOME/scripts/mpv-yt"

# 3. Build the menu
# We extract the URL from the comment line (#),
# then create a "Title | URL" format for Fuzzel
menu_data=$(ls -t "$WATCH_LATER_DIR" | xargs -I {} grep -h "^#" "$WATCH_LATER_DIR/{}" | while read -r line; do
  url=$(echo "$line" | sed 's/^# //')
  # Create a 'clean' title: remove 'https://', 'www.', and file extensions
  title=$(echo "$url" | sed -E 's|https?://(www\.)?||; s|/videos/| Twitch: |; s|watch\?v=| YouTube: |; s|\.[a-z0-9]+$||; s|.*/||')
  echo "$title | $url"
done)

# 4. Show Fuzzel
choice=$(echo "$menu_data" | fuzzel -d -p "> " -w 100)

# 5. Extract the URL from the choice and launch
if [ -n "$choice" ]; then
  final_url=$(echo "$choice" | awk -F ' | ' '{print $NF}')
  # Launching your launcher in the background
  $LAUNCHER "$final_url" &
fi
