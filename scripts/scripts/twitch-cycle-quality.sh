#!/bin/bash
TWITCH_CONTEXT="/tmp/twitch-stream-context.conf"
YT_CONTEXT="/tmp/youtube-stream-context.conf"
QUALITY_FILE="/tmp/current-quality.txt"

# Detect what's playing — check if streamlink is running (Twitch) or just mpv (YouTube)
# Prioritize Twitch detection
if [ -f "$TWITCH_CONTEXT" ]; then
  MODE="twitch"
  source "$TWITCH_CONTEXT"
# Fallback to YouTube detection
elif [ -f "$YT_CONTEXT" ]; then
  MODE="youtube"
  source "$YT_CONTEXT"
else
  notify-send "Quality" "No context files found in /tmp/"
  exit 1
fi

# --- Quality cycling ---
if [[ "$MODE" == "twitch" ]]; then
  QUALITIES=("best" "720p60" "480p" "360p")
  CURRENT=$(cat "$QUALITY_FILE" 2>/dev/null || echo "best")

  NEXT=""
  for i in "${!QUALITIES[@]}"; do
    if [ "${QUALITIES[$i]}" == "$CURRENT" ]; then
      NEXT_INDEX=$(((i + 1) % ${#QUALITIES[@]}))
      NEXT="${QUALITIES[$NEXT_INDEX]}"
      break
    fi
  done
  NEXT=${NEXT:-"best"}

  notify-send "Twitch Quality" "Switching to $NEXT..." -t 3000

  MPV_SOCKET="/tmp/mpv-twitch-ipc"

  SL_ARGS=(--twitch-low-latency --twitch-disable-ads
    --stream-segment-threads 3
    --stream-segment-attempts 3
    --stream-segment-timeout 10
    --hls-live-edge 1
    --retry-streams 2
    --retry-open 2)
  TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)
  [ -n "$TWITCH_TOKEN" ] && SL_ARGS+=(--twitch-api-header "Authorization=OAuth $TWITCH_TOKEN")

  case "$NEXT" in
    best)   SL_QUALITY="best,1080p60,1080p,720p60,720p" ;;
    720p60) SL_QUALITY="720p60,720p,best" ;;
    480p)   SL_QUALITY="480p,360p,worst" ;;
    360p)   SL_QUALITY="360p,worst" ;;
    *)      SL_QUALITY="$NEXT" ;;
  esac

  NEW_URL=$(streamlink "${SL_ARGS[@]}" --stream-url "$URL" "$SL_QUALITY" 2>/dev/null)
  if [ -z "$NEW_URL" ]; then
    notify-send "Twitch Quality" "Failed to resolve $NEXT URL" -u critical
    exit 1
  fi

  # Prefer in-place URL swap via mpv IPC — same path twitch-launcher.sh
  # uses for its low→best upgrade. No flicker, keeps the same window.
  if [ -S "$MPV_SOCKET" ]; then
    IPC_CMD=$(jq -cn --arg url "$NEW_URL" '{"command": ["loadfile", $url, "replace"]}')
    if echo "$IPC_CMD" | socat - "$MPV_SOCKET" >/dev/null 2>&1; then
      echo "$NEXT" >"$QUALITY_FILE"
      exit 0
    fi
  fi

  # Fallback: IPC unavailable. Kill the previous twitch mpv specifically
  # (matched by its IPC socket arg, so other mpv instances are spared)
  # plus any stray streamlink player wrapper, then start fresh.
  pkill -f "input-ipc-server=$MPV_SOCKET" 2>/dev/null
  pkill -f "streamlink.*--player" 2>/dev/null
  rm -f "$MPV_SOCKET"

  ASPECT_ARGS=()
  if hyprctl monitors -j 2>/dev/null | jq -e '.[] | select(.disabled == false and (.description | test("LG ULTRAGEAR"))) ' >/dev/null; then
    ASPECT_ARGS=(--panscan=1.0)
  fi

  mpv \
    --cache=yes \
    --force-window=immediate \
    --vo=gpu \
    --gpu-api=opengl \
    --hwdec=auto \
    "${ASPECT_ARGS[@]}" \
    --profile=low-latency \
    --video-sync=audio \
    --no-interpolation \
    --input-ipc-server="$MPV_SOCKET" \
    "$NEW_URL" >/dev/null 2>&1 &
  disown

  echo "$NEXT" >"$QUALITY_FILE"

elif [[ "$MODE" == "youtube" ]]; then
  YT_QUALITIES=("1080" "720" "480")
  YT_LABELS=("1080p" "720p" "480p")
  # Default to 4k
  # CURRENT=$(cat "$QUALITY_FILE" 2>/dev/null || echo "2160")
  # Default to 1080p
  CURRENT=$(cat "$QUALITY_FILE" 2>/dev/null || echo "1080")

  NEXT=""
  LABEL=""
  for i in "${!YT_QUALITIES[@]}"; do
    if [ "${YT_QUALITIES[$i]}" == "$CURRENT" ]; then
      NEXT_INDEX=$(((i + 1) % ${#YT_QUALITIES[@]}))
      NEXT="${YT_QUALITIES[$NEXT_INDEX]}"
      LABEL="${YT_LABELS[$NEXT_INDEX]}"
      break
    fi
  done
  NEXT=${NEXT:-"1080"}
  LABEL=${LABEL:-"1080p"}
  echo "$NEXT" >"$QUALITY_FILE"

  notify-send "YouTube Quality" "Switching to $LABEL..." -t 3000
  pkill mpv 2>/dev/null
  sleep 0.5
  mpv --ytdl-format="bestvideo[height<=$NEXT]+bestaudio/best" \
    --ytdl-raw-options=cookies-from-browser=firefox \
    "$YT_URL" &
  disown
fi
