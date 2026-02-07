#!/bin/bash

# Configuration
USERNAME_LIST="$HOME/scripts/twitch_usernames.txt"
TWITCH_TOKEN_FILE="$HOME/.newsboat/.twitch_oauth"
IMAGE_CACHE="$HOME/.cache/twitch-profiles"
CLIENT_ID="kimne78kx3ncx6brgo4mv6wki5h1ko"

exec >>/tmp/twitch-stream-debug.log 2>&1

# --- 1. Setup ---

if [ ! -f "$USERNAME_LIST" ]; then
  notify-send "Twitch Error" "Username list not found: $USERNAME_LIST" -t 5000 -u critical
  exit 1
fi

mkdir -p "$IMAGE_CACHE"

# --- 2. Fetch profile images ---

USERNAMES=$(cat "$USERNAME_LIST" | awk '{print $1}' | sort)

for user in $USERNAMES; do
  IMG_PATH="$IMAGE_CACHE/${user}.png"
  if [ ! -f "$IMG_PATH" ]; then
    IMG_URL=$(curl -s -H "Client-Id: $CLIENT_ID" \
      -X POST -d "{\"query\":\"query{user(login:\\\"${user}\\\"){profileImageURL(width:70)}}\"}" \
      "https://gql.twitch.tv/gql" | jq -r '.data.user.profileImageURL')
    if [ -n "$IMG_URL" ] && [ "$IMG_URL" != "null" ]; then
      curl -s -o "$IMG_PATH" "$IMG_URL"
    fi
  fi
done

# --- 3. Build wofi list with images ---

WOFI_LIST=""
for user in $USERNAMES; do
  IMG_PATH="$IMAGE_CACHE/${user}.png"
  if [ -f "$IMG_PATH" ]; then
    WOFI_LIST+="img:${IMG_PATH}:text:${user}\n"
  else
    WOFI_LIST+="${user}\n"
  fi
done

CHOICE=$(echo -e "$WOFI_LIST" | wofi --dmenu --prompt "Select Twitch Streamer" --width 800 --lines 15 --allow-images)

if [ -z "$CHOICE" ]; then
  exit 0
fi

STREAMER_USERNAME=$(echo "$CHOICE" | sed 's/.*:text://' | awk '{print $1}')
STREAMER="$STREAMER_USERNAME"
URL="https://www.twitch.tv/$STREAMER_USERNAME"

# --- 4. Stream Execution Logic ---

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
