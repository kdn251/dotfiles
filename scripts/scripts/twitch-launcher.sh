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
# Logic: Merge counts with usernames, sort by count (desc), then format for fuzzel
CHOICE=$(
  awk -v stats="$STATS_FILE" -v p="$PIXMAPS" '
    BEGIN {
      while ((getline < stats) > 0) {
        count[$1] = $2
      }
    }
    {
      # Store the first word (Username) for the icon and stats
      user_id = $1
      gsub(/[[:space:]\r]+$/, "", user_id)
      lower_id = tolower(user_id)
      
      # Store the FULL LINE (Username + Category) for the display label
      full_label = $0
      gsub(/[\r]+$/, "", full_label) # Strip carriage returns
      
      c = (count[user_id] ? count[user_id] : 0)
      
      # Print: SortCount|FullLabel \0 icon \x1f path/lowercase.png
      printf "%05d|%s\000icon\x1f%s/%s.png\n", c, full_label, p, lower_id
    }' "$USERNAME_LIST" |
    sort -rn |
    awk -F'|' '
      NR <= 5 { sub(/^[0-9]+\|/, ""); print; next }
      { others[NR] = $0 }
      END {
        for (i in others) print others[i] | "sort -t\"|\" -k2"
      }' |
    sed 's/^[0-9]*|//' |
    fuzzel --dmenu \
      --prompt "󰕃  " \
      --line-height 35 \
      --width 45 \
      --lines 10
)

if [ -z "$CHOICE" ]; then
  exit 0
fi

if [ -n "$CHOICE" ]; then
  awk -v user="$STREAMER_USERNAME" '
    BEGIN { found=0 }
    $1 == user { $2=$2+1; found=1 }
    { print $1, $2 }
    END { if (!found) print user, 1 }
  ' "$STATS_FILE" >"${STATS_FILE}.tmp" && mv "${STATS_FILE}.tmp" "$STATS_FILE"
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
    --gpu-api=opengl \
    --hwdec=auto \
    --profile=low-latency \
    --video-sync=audio \
    --no-interpolation \
    --scale=spline36 \
    --cscale=spline36 \
    --dscale=mitchell \
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
