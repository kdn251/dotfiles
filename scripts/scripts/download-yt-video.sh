#!/bin/bash
# ~/scripts/mpv-yt-download.sh
# Downloads the currently playing YouTube video organized by channel name
# Writes progress to /tmp/mpv-yt-download-status for waybar

LOG="/tmp/mpv-yt-download.log"
STATUS="/tmp/mpv-yt-download-status"
exec >>"$LOG" 2>&1
echo "--- Download triggered at $(date) ---"

# Read the URL from the context file written by mpv-picker
URL=$(grep -oP '(?<=YT_URL=").*(?=")' /tmp/youtube-stream-context.conf)

if [[ -z "$URL" ]]; then
  echo "No URL found"
  notify-send "MPV Download" "No YouTube URL found"
  exit 1
fi

# Check if a download is already running
if [[ -f "$STATUS" ]]; then
  notify-send "MPV Download" "Download already in progress"
  exit 1
fi

echo "Downloading: $URL"
echo '{"text":"  starting...","class":"downloading"}' >"$STATUS"
notify-send "MPV Download" "Starting download..."

yt-dlp \
  --cookies-from-browser firefox \
  -o "$HOME/Videos/downloads/%(channel)s/%(title)s.%(ext)s" \
  --restrict-filenames \
  --no-overwrites \
  --merge-output-format mp4 \
  --newline \
  "$URL" 2>&1 | while IFS= read -r line; do
  echo "$line" >>"$LOG"
  # Parse yt-dlp progress lines like: [download]  45.2% of  120.50MiB at  5.23MiB/s ETA 00:12
  if [[ "$line" =~ \[download\].*([0-9]+\.[0-9]+)%.*at[[:space:]]+([0-9.]+[KMG]iB/s).*ETA[[:space:]]+([0-9:]+) ]]; then
    PCT="${BASH_REMATCH[1]}"
    SPEED="${BASH_REMATCH[2]}"
    ETA="${BASH_REMATCH[3]}"
    echo "{\"text\":\"  ${PCT}% ${SPEED} ETA ${ETA}\",\"class\":\"downloading\"}" >"$STATUS"
  elif [[ "$line" =~ \[download\].*([0-9]+\.[0-9]+)% ]]; then
    PCT="${BASH_REMATCH[1]}"
    echo "{\"text\":\"  ${PCT}%\",\"class\":\"downloading\"}" >"$STATUS"
  elif [[ "$line" =~ \[Merger\]|Merging ]]; then
    echo '{"text":"  merging...","class":"downloading"}' >"$STATUS"
  fi
done

EXIT_CODE=${PIPESTATUS[0]}

if [[ $EXIT_CODE -eq 0 ]]; then
  echo '{"text":"  done!","class":"done"}' >"$STATUS"
  notify-send "MPV Download" "Download complete!"
  echo "Done successfully"
  sleep 5
else
  echo '{"text":"  failed","class":"failed"}' >"$STATUS"
  notify-send "MPV Download" "Download failed — check log"
  echo "Failed"
  sleep 5
fi

rm -f "$STATUS"
