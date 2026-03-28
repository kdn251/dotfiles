#!/bin/bash
# Configuration
USERNAME_LIST="$HOME/scripts/twitch_usernames.txt"
TWITCH_TOKEN_FILE="$HOME/.newsboat/.twitch_oauth"
IMAGE_CACHE="$HOME/.cache/twitch-profiles"
PIXMAPS="$HOME/.local/share/pixmaps"
CLIENT_ID="kimne78kx3ncx6brgo4mv6wki5h1ko"
MPV_SOCKET="/tmp/mpv-twitch-ipc"
exec >>/tmp/twitch-stream-debug.log 2>&1

# --- 1. Setup & Force Icon Sync ---
if [ ! -f "$USERNAME_LIST" ]; then
  notify-send "Twitch Error" "Username list not found" -t 5000 -u critical
  exit 1
fi
mkdir -p "$IMAGE_CACHE"
mkdir -p "$PIXMAPS"

# Ensure all cached images are available in the pixmaps directory
ln -sf "$IMAGE_CACHE/"*.png "$PIXMAPS/" 2>/dev/null

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
          ln -sf "$IMG_PATH" "$PIXMAPS/${user}.png"
        fi
      ) &
    fi
  done
  wait
fi

# --- 3. Build fuzzel list & Launch ---
# Direct pipe from awk to fuzzel preserves the \0 and \x1f characters.
# We use printf in awk to generate the exact byte sequence fuzzel needs.
CHOICE=$(
  awk '{printf "%s\0icon\x1f%s\n", $1, $1}' "$USERNAME_LIST" | sort | fuzzel --dmenu \
    --prompt "󰕃  " \
    --width 40 \
    --line-height 25 \
    --width 35
  --lines 10
)

if [ -z "$CHOICE" ]; then
  exit 0
fi

# Extract username (fuzzel returns the label part)
STREAMER_USERNAME=$(echo "$CHOICE" | awk '{print $1}')
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
    pkillall chatterino
    chatterino --channels "$STREAMER_USERNAME" >/dev/null 2>&1
  ) &

  IMG_PATH="$PIXMAPS/${STREAMER_USERNAME}.png"
  if [ -f "$IMG_PATH" ]; then
    notify-send -i "$IMG_PATH" "MPV" "Loading $STREAMER stream..." -t 2000 -u low &
  else
    notify-send "MPV" "Loading $STREAMER stream..." -t 2000 -u low &
  fi

  # Build streamlink auth args
  SL_ARGS=(--twitch-low-latency --twitch-disable-ads)
  TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)
  [ -n "$TWITCH_TOKEN" ] && SL_ARGS+=(--twitch-api-header "Authorization=OAuth $TWITCH_TOKEN")

  SL_COMMON=(
    "${SL_ARGS[@]}"
    --stream-segment-threads 3
    --stream-segment-attempts 3
    --stream-segment-timeout 10
    --hls-live-edge 1
    --retry-streams 2
    --retry-open 2
  )

  pkill mpv
  rm -f "$MPV_SOCKET"

  LOW_URL=$(streamlink "${SL_COMMON[@]}" --stream-url "$URL" 480p,360p,worst 2>/dev/null)

  if [ -z "$LOW_URL" ]; then
    streamlink "${SL_COMMON[@]}" --player mpv "$URL" best,720p,480p
    exit $?
  fi

  mpv \
    --cache=yes \
    --force-window=immediate \
    --vo=gpu \
    --hwdec=auto \
    --profile=low-latency \
    --demuxer-max-bytes=500KiB \
    --demuxer-readahead-secs=2 \
    --demuxer-lavf-o=fflags=+nobuffer \
    --input-ipc-server="$MPV_SOCKET" \
    "$LOW_URL" &
  MPV_PID=$!

  (
    for i in $(seq 1 20); do
      [ -S "$MPV_SOCKET" ] && break
      sleep 0.1
    done
    [ ! -S "$MPV_SOCKET" ] && exit 1
    BEST_URL=$(streamlink "${SL_COMMON[@]}" --stream-url "$URL" best,1080p60,1080p,720p60,720p 2>/dev/null)
    if [ -n "$BEST_URL" ]; then
      IPC_CMD=$(jq -cn --arg url "$BEST_URL" '{"command": ["loadfile", $url, "replace"]}')
      echo "$IPC_CMD" | socat - "$MPV_SOCKET" >/dev/null 2>&1
      notify-send "MPV" "Quality upgraded ✓" -t 1500 -u low
    fi
  ) &

  wait $MPV_PID
) &
