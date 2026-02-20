#!/bin/bash
# ~/scripts/waybar-yt-download.sh
# Waybar custom module — reads yt-dlp download progress

STATUS="/tmp/mpv-yt-download-status"

if [[ -f "$STATUS" ]]; then
  cat "$STATUS"
else
  echo '{"text":"","class":"idle"}'
fi
