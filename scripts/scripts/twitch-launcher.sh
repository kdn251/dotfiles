#!/bin/bash

# Configuration
USERNAME_LIST="$HOME/scripts/twitch_usernames.txt"
TWITCH_TOKEN_FILE="$HOME/.newsboat/.twitch_oauth"

exec >>/tmp/twitch-stream-debug.log 2>&1

# --- 1. Wofi Selection Logic ---

if [ ! -f "$USERNAME_LIST" ]; then
  echo "ERROR: Username list not found: $USERNAME_LIST"
  notify-send "Twitch Error" "Username list not found: $USERNAME_LIST" -t 5000 -u critical
  exit 1
fi

CHOICE=$(cat "$USERNAME_LIST" | sort | wofi --dmenu --prompt "Select Twitch Streamer" --width 800 --lines 15)

if [ -z "$CHOICE" ]; then
  echo "INFO: Selection cancelled."
  exit 0
fi

STREAMER_USERNAME=$(echo "$CHOICE" | awk '{print $1}')
STREAMER="$STREAMER_USERNAME"
URL="https://www.twitch.tv/$STREAMER_USERNAME"

# --- 2. Stream Execution Logic ---

(
  echo "========== DEBUG =========="
  echo "URL constructed: $URL"
  echo "Streamer selected: $STREAMER"
  date

  CONTEXT_FILE="/tmp/twitch-stream-context.conf"
  echo "URL=\"$URL\"" >"$CONTEXT_FILE"
  echo "STREAMER_USERNAME=\"$STREAMER_USERNAME\"" >>"$CONTEXT_FILE"
  echo "TWITCH_TOKEN_FILE=\"$TWITCH_TOKEN_FILE\"" >>"$CONTEXT_FILE"

  pkill chatterino
  chatterino --channels "$STREAMER_USERNAME" >/dev/null 2>&1 &
  echo "INFO: Launched Chatterino for $STREAMER_USERNAME."

  pkill -f "streamlink.*--player" 2>/dev/null

  TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)

  notify-send "MPV" "Loading $STREAMER stream..." -t 2000 -u low

  if [ -n "$TWITCH_TOKEN" ]; then
    streamlink \
      --twitch-low-latency \
      --twitch-disable-ads \
      --twitch-api-header "Authorization=OAuth $TWITCH_TOKEN" \
      --player mpv \
      --player-args "--cache=yes --force-window=immediate --vo=gpu" \
      --stream-segment-threads 3 \
      --stream-segment-attempts 3 \
      --stream-segment-timeout 10 \
      --retry-streams 2 \
      --retry-open 2 \
      "$URL" best,720p,480p
  else
    streamlink \
      --twitch-low-latency \
      --twitch-disable-ads \
      --player mpv \
      --player-args "--cache=yes --force-window=immediate --vo=gpu" \
      "$URL" best,720p,480p
  fi
) &
