#!/bin/bash
TWITCH_CONTEXT="/tmp/twitch-stream-context.conf"
YT_CONTEXT="/tmp/youtube-stream-context.conf"
QUALITY_FILE="/tmp/current-quality.txt"

# Detect what's playing — check if streamlink is running (Twitch) or just mpv (YouTube)
if pgrep -f "streamlink.*--player" >/dev/null 2>&1 && [ -f "$TWITCH_CONTEXT" ]; then
  MODE="twitch"
  source "$TWITCH_CONTEXT"
elif [ -f "$YT_CONTEXT" ]; then
  MODE="youtube"
  source "$YT_CONTEXT"
else
  notify-send "Quality" "No active stream found"
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
  echo "$NEXT" >"$QUALITY_FILE"

  notify-send "Twitch Quality" "Switching to $NEXT..." -t 3000
  pkill -f "streamlink.*--player" 2>/dev/null

  TWITCH_TOKEN=$(cat "$TWITCH_TOKEN_FILE" 2>/dev/null)
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
      "$URL" "$NEXT" >/dev/null 2>&1 &
  else
    streamlink \
      --twitch-low-latency \
      --twitch-disable-ads \
      --player mpv \
      --player-args "--cache=yes --force-window=immediate --vo=gpu" \
      "$URL" "$NEXT" >/dev/null 2>&1 &
  fi

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
