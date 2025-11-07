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
# Use percentage of screen height (e.g., 50% of 1080 / 36 ≈ 15 lines)
# Get screen height
SCREEN_HEIGHT=$(hyprctl monitors -j | jq -r '.[0].height')

# Calculate reasonable number of lines (e.g., 40% of screen, assuming ~20px per line)
# Adjust the divisor based on your font size and preferences
DMENU_LINES=$((SCREEN_HEIGHT / 36)) # 36px per line is a reasonable default

# Set a reasonable min/max
DMENU_LINES=$((DMENU_LINES < 10 ? 10 : DMENU_LINES)) # Minimum 10 lines
DMENU_LINES=$((DMENU_LINES > 40 ? 40 : DMENU_LINES)) # Maximum 40 lines
DMENU_ARGS="-i -l $DMENU_LINES"
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

  # --- NEW: Save Stream Context ---
  CONTEXT_FILE="/tmp/twitch-stream-context.conf"

  # Save the necessary variables to a file for the hotkey script to use
  # to change the quality of the stream if needed
  echo "URL=\"$URL\"" >"$CONTEXT_FILE"
  echo "STREAMER_USERNAME=\"$STREAMER_USERNAME\"" >>"$CONTEXT_FILE"
  echo "TWITCH_TOKEN_FILE=\"$TWITCH_TOKEN_FILE\"" >>"$CONTEXT_FILE"
  # ---------------------------------

  # Kill existing chatterino instance
  # before starting next instance
  pkill chatterino

  # --- NEW: Launch Chatterino Chat Window ---
  # The '--channels' argument opens a new tab/split for the chosen streamer.
  # The '&' sends the GUI application to the background so the script can proceed to Streamlink.
  chatterino --channels "$STREAMER_USERNAME" >/dev/null 2>&1 &
  echo "INFO: Launched Chatterino for $STREAMER_USERNAME."
  # -----------------------------------------

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
