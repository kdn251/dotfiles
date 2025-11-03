#!/bin/bash

# Configuration
# Path to the file containing streamer usernames, one per line
USERNAME_LIST="$HOME/scripts/twitch_usernames.txt"
# Path to your Twitch OAuth token file
TWITCH_TOKEN_FILE="$HOME/.newsboat/.twitch_oauth"

exec >>/tmp/twitch-stream-debug.log 2>&1

# --- 1. Dmenu Selection Logic ---

# Check if the list file exists
if [ ! -f "$USERNAME_LIST" ]; then
  echo "ERROR: Username list not found: $USERNAME_LIST"
  notify-send "Twitch DMenu Error" "Username list not found: $USERNAME_LIST" -t 5000 -u critical
  exit 1
fi

# Define your dmenu arguments here for easy customization
DMENU_ARGS="-i -l 10"                                          # Keep interactive mode and 10 lines
DMENU_COLORS="-nb #282828 -nf #ebdbb2 -sb #00FFFF -sf #282828" # Dark background, light text, orange selection
DMENU_FONT="-fn Monospace-12"

# Read the usernames and pipe them to dmenu
CHOICE=$(cat "$USERNAME_LIST" | sort | dmenu $DMENU_ARGS $DMENU_COLORS $DMENU_FONT -p "Select Twitch Streamer:")

# Check if a choice was made
if [ -z "$CHOICE" ]; then
  echo "INFO: Dmenu selection cancelled."
  exit 0
fi

# Strip the game part - only keep the username before the space and parenthesis
STREAMER_USERNAME=$(echo "$CHOICE" | sed 's/ (.*//' | tr -d '[:space:]')
STREAMER="$STREAMER_USERNAME" # Use STREAMER for compatibility with your existing logic

# Construct the full Twitch channel URL
URL="https://www.twitch.tv/$STREAMER_USERNAME" # Use URL for logging/mpv logic

# --- 2. Stream Execution Logic (Adapted from your script) ---

# Fork the entire process immediately so newsboat doesn't wait
(
  # Log to debug file
  echo "========== DEBUG =========="
  echo "URL constructed: $URL"
  echo "Streamer selected: $STREAMER"
  date

  # Kill existing streams (using pkill -f "streamlink" is usually safer)
  pkill -f "streamlink.*--player" 2>/dev/null

  # Read OAuth token
  TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)

  notify-send "MPV" "Loading $STREAMER stream..." -t 2000 -u low

  # Launch stream with streamlink
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
      "$URL" best,720p,480p
  else
    streamlink \
      --twitch-low-latency \
      --twitch-disable-ads \
      --player mpv \
      --player-args "--cache=yes --force-window=immediate" \
      "$URL" best,720p,480p
  fi
) &
