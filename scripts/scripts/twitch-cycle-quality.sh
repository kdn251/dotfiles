#!/bin/bash
TWITCH_CONTEXT="/tmp/twitch-stream-context.conf"
YT_CONTEXT="/tmp/youtube-stream-context.conf"
QUALITY_FILE="/tmp/current-quality.txt"
# Separate file per service: the two cycles use different labels, and sharing
# one file meant switching between Twitch and YouTube resumed mid-cycle on a
# label the other service does not have.
YT_QUALITY_FILE="/tmp/current-quality-youtube.txt"
TWITCH_SOCKET="/tmp/mpv-twitch-ipc"
YT_SOCKET="/tmp/mpv-yt-ipc"
TWITCH_ICON="/usr/share/icons/Papirus/48x48/apps/gnome-twitch.svg"

# Which player is actually running, decided by asking the IPC sockets rather
# than by which context file exists. The context files are never cleaned up, so
# /tmp/twitch-stream-context.conf survives long after the stream ended and made
# this always pick Twitch -- pressing the key during a YouTube video either did
# nothing or restarted a Twitch stream.
alive() { [ -S "$1" ] && echo '{"command":["get_property","time-pos"]}' |
  timeout 2 socat - "$1" 2>/dev/null | grep -q '"error":"success"'; }

MODE=""
if alive "$TWITCH_SOCKET"; then
  MODE="twitch"
  [ -f "$TWITCH_CONTEXT" ] && source "$TWITCH_CONTEXT"
elif alive "$YT_SOCKET"; then
  MODE="youtube"
  [ -f "$YT_CONTEXT" ] && source "$YT_CONTEXT"
else
  # Deliberately no fall back to "whichever context file exists". Those files
  # are never removed, so with nothing playing the stale Twitch one made this
  # key START a Twitch stream out of nowhere -- observed while testing, from a
  # press meant for a YouTube video.
  notify-send -a "Quality" "Quality" "Nothing is playing"
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

  notify-send -i "$TWITCH_ICON" "Twitch Quality" "Switching to $NEXT..." -t 3000

  MPV_SOCKET="/tmp/mpv-twitch-ipc"

  SL_ARGS=(--twitch-disable-ads
    --stream-segment-threads 3
    --stream-segment-attempts 5
    --stream-segment-timeout 15
    --hls-live-edge 3
    --ringbuffer-size 32M
    --retry-streams 5
    --retry-open 3)
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
    notify-send -i "$TWITCH_ICON" "Twitch Quality" "Failed to resolve $NEXT URL" -u critical
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
    --input-ipc-server="$MPV_SOCKET" \
    "$NEW_URL" >/dev/null 2>&1 &
  disown

  echo "$NEXT" >"$QUALITY_FILE"

elif [[ "$MODE" == "youtube" ]]; then
  # Same ladder as Twitch so one key behaves the same whatever is playing.
  QUALITIES=("best" "720p60" "480p" "360p")
  CURRENT=$(cat "$YT_QUALITY_FILE" 2>/dev/null || echo "best")
  NEXT=""
  for i in "${!QUALITIES[@]}"; do
    if [ "${QUALITIES[$i]}" == "$CURRENT" ]; then
      NEXT="${QUALITIES[$(((i + 1) % ${#QUALITIES[@]}))]}"
      break
    fi
  done
  NEXT=${NEXT:-"best"}

  case "$NEXT" in
  best)   FMT="bestvideo+bestaudio/best" ;;
  720p60) FMT="bestvideo[height<=720]+bestaudio/best[height<=720]/best" ;;
  480p)   FMT="bestvideo[height<=480]+bestaudio/best[height<=480]/best" ;;
  360p)   FMT="bestvideo[height<=360]+bestaudio/best[height<=360]/best" ;;
  esac

  # Prefer the URL the player is actually on: mpv keeps the original watch URL
  # in "path" even while playing the resolved streams, so it stays right if the
  # video was changed without the context file being rewritten.
  if alive "$YT_SOCKET"; then
    LIVE_URL=$(echo '{"command":["get_property","path"]}' |
      timeout 3 socat - "$YT_SOCKET" 2>/dev/null | jq -r '.data // empty')
    POS=$(echo '{"command":["get_property","time-pos"]}' |
      timeout 3 socat - "$YT_SOCKET" 2>/dev/null | jq -r '.data // empty')
  fi
  URL_TO_PLAY="${LIVE_URL:-${YT_URL:-}}"
  if [ -z "$URL_TO_PLAY" ]; then
    notify-send -a "Quality" -u critical "YouTube Quality" "Could not tell which video is playing"
    exit 1
  fi

  NOTIFY_ARGS=(-a "Quality" -t 3000)
  [ -n "${YT_ICON:-}" ] && [ -f "${YT_ICON:-}" ] && NOTIFY_ARGS+=(-i "$YT_ICON")

  if alive "$YT_SOCKET"; then
    # Reload the same URL with a new ytdl-format, resuming at the current
    # position. The old version ran `pkill mpv` -- which also killed any other
    # mpv, Twitch included -- and restarted the video from the beginning.
    CMD=$(jq -cn --arg u "$URL_TO_PLAY" --arg s "${POS:-0}" --arg f "$FMT" \
      '{"command":["loadfile",$u,"replace",0,{"start":$s,"ytdl-format":$f}]}')
    if echo "$CMD" | timeout 6 socat - "$YT_SOCKET" 2>/dev/null | grep -q '"error":"success"'; then
      echo "$NEXT" >"$YT_QUALITY_FILE"
      notify-send "${NOTIFY_ARGS[@]}" "${YT_TITLE:-YouTube}" "Quality: $NEXT"
      exit 0
    fi
  fi

  # No player to talk to: start one at the requested quality. mpv-yt resolves
  # yt-dlp itself, which matters because the pacman copy cannot play these.
  notify-send "${NOTIFY_ARGS[@]}" "${YT_TITLE:-YouTube}" "Quality: $NEXT"
  echo "$NEXT" >"$YT_QUALITY_FILE"
  YTDL="$HOME/.local/bin/yt-dlp"
  [ -x "$YTDL" ] || YTDL=$(command -v yt-dlp 2>/dev/null)
  setsid -f mpv "--script-opts=ytdl_hook-ytdl_path=$YTDL" \
    --ytdl-format="$FMT" \
    --input-ipc-server="$YT_SOCKET" \
    ${POS:+--start="$POS"} \
    "$URL_TO_PLAY" >/dev/null 2>&1 &
fi
