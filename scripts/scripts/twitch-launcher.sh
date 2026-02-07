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

# --- 2. Fetch profile images in parallel ---
USERNAMES=$(awk '{print $1}' "$USERNAME_LIST" | sort)
MISSING=0
for user in $USERNAMES; do
  [ ! -f "$IMAGE_CACHE/${user}.png" ] && MISSING=1 && break
done

if [ "$MISSING" -eq 1 ]; then
  for user in $USERNAMES; do
    IMG_PATH="$IMAGE_CACHE/${user}.png"
    if [ ! -f "$IMG_PATH" ]; then
      (
        IMG_URL=$(curl -s --max-time 2 -H "Client-Id: $CLIENT_ID" \
          -X POST -d "{\"query\":\"query{user(login:\\\"${user}\\\"){profileImageURL(width:70)}}\"}" \
          "https://gql.twitch.tv/gql" | jq -r '.data.user.profileImageURL')
        if [ -n "$IMG_URL" ] && [ "$IMG_URL" != "null" ]; then
          curl -s --max-time 2 -o "$IMG_PATH" "$IMG_URL"
        fi
      ) &
    fi
  done
  wait
fi

# --- 3. Build wofi list ---
WOFI_LIST=""
while IFS= read -r line; do
  user=$(echo "$line" | awk '{print $1}')
  IMG_PATH="$IMAGE_CACHE/${user}.png"
  if [ -f "$IMG_PATH" ]; then
    WOFI_LIST+="img:${IMG_PATH}:text:${line}\n"
  else
    WOFI_LIST+="${line}\n"
  fi
done < <(sort "$USERNAME_LIST")

CHOICE=$(echo -e "$WOFI_LIST" | wofi --dmenu --prompt "Select Twitch Streamer" --width 800 --lines 15 --allow-images)
if [ -z "$CHOICE" ]; then
  exit 0
fi

STREAMER_USERNAME=$(echo "$CHOICE" | sed 's/.*:text://' | awk '{print $1}')
STREAMER="$STREAMER_USERNAME"
URL="https://www.twitch.tv/$STREAMER_USERNAME"

# --- 4. Stream Execution ---
(
  echo "========== DEBUG =========="
  echo "URL: $URL | Streamer: $STREAMER | $(date)"

  echo "URL=\"$URL\"" >/tmp/twitch-stream-context.conf
  echo "STREAMER_USERNAME=\"$STREAMER_USERNAME\"" >>/tmp/twitch-stream-context.conf
  echo "TWITCH_TOKEN_FILE=\"$TWITCH_TOKEN_FILE\"" >>/tmp/twitch-stream-context.conf

  (
    pkill chatterino
    chatterino --channels "$STREAMER_USERNAME" >/dev/null 2>&1
  ) &

  IMG_PATH="$HOME/.cache/twitch-profiles/${STREAMER_USERNAME}.png"
  if [ -f "$IMG_PATH" ]; then
    notify-send -i "$IMG_PATH" "MPV" "Loading $STREAMER stream..." -t 2000 -u low &
  else
    notify-send "MPV" "Loading $STREAMER stream..." -t 2000 -u low &
  fi

  SL_ARGS=(--twitch-low-latency --twitch-disable-ads)
  TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)
  [ -n "$TWITCH_TOKEN" ] && SL_ARGS+=(--twitch-api-header "Authorization=OAuth $TWITCH_TOKEN")

  streamlink "${SL_ARGS[@]}" \
    --player mpv \
    --player-args "--cache=yes --force-window=immediate --vo=gpu --hwdec=auto --profile=low-latency --demuxer-max-bytes=500KiB --demuxer-readahead-secs=2 --demuxer-lavf-o=fflags=+nobuffer" \
    --stream-segment-threads 3 \
    --stream-segment-attempts 3 \
    --stream-segment-timeout 10 \
    --hls-live-edge 1 \
    --retry-streams 2 \
    --retry-open 2 \
    "$URL" best,720p,480p
) &
