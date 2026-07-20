#!/bin/bash
# Configuration
USERNAME_LIST="$HOME/scripts/twitch_usernames.txt"
TWITCH_TOKEN_FILE="$HOME/.newsboat/.twitch_oauth"
IMAGE_CACHE="$HOME/.cache/twitch-profiles"
PIXMAPS="$HOME/.local/share/pixmaps"
STATS_FILE="$HOME/.cache/twitch_stats.txt"
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
touch "$STATS_FILE"

# Ensure all cached images are available in the pixmaps directory
ln -sf "$IMAGE_CACHE/"*.png "$PIXMAPS/" 2>/dev/null

# --- 2. Fetch profile images in parallel ---
USERNAMES=$(awk '{print $1}' "$USERNAME_LIST" | sort)
MISSING=0
for user in $USERNAMES; do
  LOWER_USER=$(echo "$user" | tr '[:upper:]' '[:lower:]')
  [ ! -f "$IMAGE_CACHE/${LOWER_USER}.png" ] && MISSING=1 && break
done

if [ "$MISSING" -eq 1 ]; then
  for user in $USERNAMES; do
    LOWER_USER=$(echo "$user" | tr '[:upper:]' '[:lower:]')
    IMG_PATH="$IMAGE_CACHE/${LOWER_USER}.png"
    if [ ! -f "$IMG_PATH" ]; then
      (
        IMG_URL=$(curl -s --max-time 3 -H "Client-Id: $CLIENT_ID" \
          -X POST -d "{\"query\":\"query{user(login:\\\"${LOWER_USER}\\\"){profileImageURL(width:70)}}\"}" \
          "https://gql.twitch.tv/gql" | jq -r '.data.user.profileImageURL')

        if [ -n "$IMG_URL" ] && [ "$IMG_URL" != "null" ]; then
          # 1. Download to a temporary location
          TEMP_IMG="/tmp/${LOWER_USER}_raw"
          curl -s --max-time 3 -o "$TEMP_IMG" "$IMG_URL"

          # 2. Force conversion to a standard PNG format for Fuzzel
          # This ensures that even if Twitch sends WebP, it becomes a real PNG
          ffmpeg -y -i "$TEMP_IMG" -vframes 1 "$IMG_PATH" >/dev/null 2>&1

          # 3. Link it to pixmaps
          ln -sf "$IMG_PATH" "$PIXMAPS/${LOWER_USER}.png"

          # 4. Cleanup
          rm -f "$TEMP_IMG"
        fi
      ) &
    fi
  done
  wait
fi

# --- 3. Build prioritized fuzzel list ---
# Top 5 most-watched live streamers (by pick count) first, then everyone
# else alphabetically. Lines in MENU_TMP: count \t lowercase-label \t label
MENU_TMP=$(mktemp)
awk -v stats="$STATS_FILE" '
  BEGIN {
    while ((getline line < stats) > 0) {
      n = split(line, a, " ")
      if (n >= 2 && a[2] ~ /^[0-9]+$/) count[a[1]] = a[2] + 0
    }
  }
  NF {
    label = $0
    gsub(/[[:space:]\r]+$/, "", label)
    user = $1
    sub(/\r$/, "", user)
    c = (user in count) ? count[user] : 0
    printf "%05d\t%s\t%s\n", c, tolower(label), label
  }' "$USERNAME_LIST" >"$MENU_TMP"

TOP5=$(sort -t"$(printf '\t')" -k1,1nr -k2,2 "$MENU_TMP" | awk -F'\t' '$1 + 0 > 0' | head -n 5)

CHOICE=$(
  {
    [ -n "$TOP5" ] && printf '%s\n' "$TOP5"
    sort -t"$(printf '\t')" -k2,2 "$MENU_TMP" | grep -vxF -f <(printf '%s\n' "$TOP5")
  } |
    awk -F'\t' -v p="$PIXMAPS" '
      NF >= 3 {
        split($3, w, " ")
        printf "%s\000icon\x1f%s/%s.png\n", $3, p, tolower(w[1])
      }' |
    fuzzel --dmenu \
      --prompt "󰕃  " \
      --line-height 35 \
      --width 45 \
      --lines 10
)
rm -f "$MENU_TMP"

if [ -z "$CHOICE" ]; then
  exit 0
fi

# Extract just the username
STREAMER_USERNAME=$(echo "$CHOICE" | awk '{print $1}')
STREAMER="$STREAMER_USERNAME"
URL="https://www.twitch.tv/$STREAMER_USERNAME"

# --- 4. Update Stats ---
# Increments the count for the selected streamer in the stats file
awk -v user="$STREAMER_USERNAME" '
  BEGIN { found=0 }
  $1 == user { $2=$2+1; found=1 }
  { print $1, $2 }
  END { if (!found) print user, 1 }
' "$STATS_FILE" >"${STATS_FILE}.tmp" && mv "${STATS_FILE}.tmp" "$STATS_FILE"

# --- 5. Stream Execution ---
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

  IMG_PATH="$PIXMAPS/${STREAMER_USERNAME,,}.png"
  if [ -f "$IMG_PATH" ]; then
    notify-send -i "$IMG_PATH" "MPV" "Loading $STREAMER stream..." -t 2000 -u low &
  else
    notify-send "MPV" "Loading $STREAMER stream..." -t 2000 -u low &
  fi

  # Build streamlink auth args
  # NOTE: --twitch-low-latency dropped on purpose. It forces playback to the
  # bleeding edge of the stream, which is the #1 cause of constant re-buffering.
  SL_ARGS=(--twitch-disable-ads)
  TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)
  [ -n "$TWITCH_TOKEN" ] && SL_ARGS+=(--twitch-api-header "Authorization=OAuth $TWITCH_TOKEN")

  SL_COMMON=(
    "${SL_ARGS[@]}"
    --stream-segment-threads 3
    --stream-segment-attempts 5
    --stream-segment-timeout 15
    --hls-live-edge 3
    --ringbuffer-size 32M
    --retry-streams 5
    --retry-open 3
  )

  pkill mpv
  rm -f "$MPV_SOCKET"

  # Pillarbox only shows up on the 16:9 LG; on the 3:2 laptop panel
  # panscan=1.0 would crop ~14% off the sides. Apply only when docked.
  ASPECT_ARGS=()
  if hyprctl monitors -j 2>/dev/null | jq -e '.[] | select(.disabled == false and (.description | test("LG ULTRAGEAR"))) ' >/dev/null; then
    ASPECT_ARGS=(--panscan=1.0)
  fi

  LOW_URL=$(streamlink "${SL_COMMON[@]}" --stream-url "$URL" 480p,360p,worst 2>/dev/null)

  if [ -z "$LOW_URL" ]; then
    streamlink "${SL_COMMON[@]}" --player mpv "$URL" best,720p,480p
    exit $?
  fi

  mpv \
    --cache=yes \
    --cache-secs=30 \
    --demuxer-max-bytes=150MiB \
    --demuxer-max-back-bytes=50MiB \
    --demuxer-readahead-secs=20 \
    --force-window=immediate \
    --vo=gpu \
    --gpu-api=opengl \
    --hwdec=auto \
    "${ASPECT_ARGS[@]}" \
    --video-sync=audio \
    --no-interpolation \
    --scale=spline36 \
    --cscale=spline36 \
    --dscale=mitchell \
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
