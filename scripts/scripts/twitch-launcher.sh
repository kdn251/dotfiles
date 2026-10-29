#!/bin/bash
# Configuration
USERNAME_LIST="$HOME/scripts/twitch_usernames.txt"
RUMBLE_LIST="$HOME/scripts/rumble_channels.tsv"
TWITCH_TOKEN_FILE="$HOME/.newsboat/.twitch_oauth"
IMAGE_CACHE="$HOME/.cache/twitch-profiles"
PIXMAPS="$HOME/.local/share/pixmaps"
STATS_FILE="$HOME/.cache/twitch_stats.txt"
CLIENT_ID="kimne78kx3ncx6brgo4mv6wki5h1ko"
MPV_SOCKET="/tmp/mpv-twitch-ipc"
CHAT_CLASS="com.chatterino.chatterino"
CHAT_LAYOUT="$HOME/.local/share/chatterino/Settings/window-layout.json"
# Marks which launcher instance owns the current stream. Relaunching over a
# running stream bumps this, so the old instance's mpv-exit cleanup sees a
# stale id and leaves the new Chatterino window alone.
SESSION_FILE="/tmp/twitch-session.id"
SESSION_ID="$$-$(date +%s%N)"
exec >>/tmp/twitch-stream-debug.log 2>&1

# All services use the same compact loading notification.
notify_loading() {
  local icon="$1" description="$2"
  local args=(-t 2000 -u low)
  [ -f "$icon" ] && args+=(-i "$icon")
  notify-send "${args[@]}" "MPV" "Loading $description stream..."
}

# MPV exits with a signal status when another stream intentionally replaces it.
# Only the current session may report a genuine player failure.
stream_session_current() {
  [ "$(cat "$SESSION_FILE" 2>/dev/null)" = "$SESSION_ID" ]
}

play_live_stream() {
  local rc
  mpv "$@"
  rc=$?
  stream_session_current || return 0
  case "$rc" in
    0|130|137|143) return 0 ;;
  esac
  notify-send "${NOTIFY_ARGS[@]}" "$STREAMER — $SERVICE" "Unable to play the live stream. Try again."
  return "$rc"
}

# --- Chatterino lifecycle ---------------------------------------------------
# One window, one tab, tied to the life of the stream.

# Ask every Chatterino window to close, then wait for the process to actually
# exit. Closing the window (rather than SIGKILLing) is what makes Chatterino
# flush Settings/settings.json, which is where the login token lives.
chat_stop() {
  local addr i
  rm -f "${XDG_RUNTIME_DIR:-/tmp}/twitch-chat-channel-${UID}"
  for addr in $(hyprctl clients -j 2>/dev/null |
    jq -r --arg c "$CHAT_CLASS" '.[] | select(.class == $c) | .address'); do
    hyprctl dispatch closewindow address:"$addr" >/dev/null 2>&1
  done
  for i in $(seq 1 40); do
    pgrep -x chatterino >/dev/null || return 0
    sleep 0.1
  done
  pkill -x chatterino
  for i in $(seq 1 20); do
    pgrep -x chatterino >/dev/null || return 0
    sleep 0.1
  done
  pkill -9 -x chatterino
}

# Same, but only if we are still the current stream (see SESSION_ID).
chat_stop_if_current() {
  manage_chat stop
}

# Start a fresh Chatterino showing exactly one tab: $1's chat.
#
# NOTE: do NOT use `--channels` here. That flag puts Chatterino in a
# throwaway-layout mode where it never writes Settings/settings.json on exit,
# so any account you add from that window is silently discarded (login
# "expires" on every restart). `--activate` is no good either: it forwards over
# the IPC socket of the running instance and *appends* a tab, which is how the
# window ended up with a tab per streamer. Instead: close the old window
# cleanly, rewrite window-layout.json down to the single tab we want, and start
# Chatterino normally so it loads that layout and still saves its settings.
chat_start() {
  local ch tmp
  ch="${1,,}"
  chat_stop
  stream_session_current || return 0

  mkdir -p "$(dirname "$CHAT_LAYOUT")"
  tmp=$(mktemp)
  # Keep the existing window geometry/state, replace its tab list wholesale.
  if ! jq --arg ch "$ch" '
        ((.windows // [])[0] // {"type": "main"}) as $w
        | {windows: [$w + {tabs: [{
            highlightsEnabled: true,
            selected: true,
            splits2: {
              data: {name: $ch, type: "twitch"},
              filters: [],
              flexh: 1,
              flexv: 1,
              moderationMode: false,
              type: "split"
            }
          }]}]}' "$CHAT_LAYOUT" >"$tmp" 2>/dev/null || [ ! -s "$tmp" ]; then
    # Missing or unreadable layout: write a minimal one from scratch.
    jq -n --arg ch "$ch" '{windows: [{
        type: "main",
        tabs: [{
          highlightsEnabled: true,
          selected: true,
          splits2: {
            data: {name: $ch, type: "twitch"},
            filters: [],
            flexh: 1,
            flexv: 1,
            moderationMode: false,
            type: "split"
          }
        }]
      }]}' >"$tmp"
  fi
  mv "$tmp" "$CHAT_LAYOUT"

  # Chatterino must not inherit the transition lock: otherwise every later
  # switch/cleanup waits for the very process it is supposed to close.
  chatterino 8>&- >/dev/null 2>&1 &
  printf '%s\n' "$ch" > "${XDG_RUNTIME_DIR:-/tmp}/twitch-chat-channel-${UID}"
}

# Serialize chat transitions without holding up playback. Recheck ownership
# after obtaining the lock: a newer selection may have overtaken this worker.
manage_chat() (
  exec 8>"${XDG_RUNTIME_DIR:-/tmp}/twitch-chat-transition-${UID}.lock"
  flock 8
  stream_session_current || exit 0
  if [ "$1" = start ]; then
    if [ "$(cat "${XDG_RUNTIME_DIR:-/tmp}/twitch-chat-channel-${UID}" 2>/dev/null)" = "${2,,}" ] && hyprctl clients -j | jq -e --arg c "$CHAT_CLASS" 'any(.[]; .class == $c)' >/dev/null; then
      exit 0
    fi
    python3 "$HOME/scripts/media-chat.py" --close-youtube
    stream_session_current || exit 0
    chat_start "$2"
  else
    chat_stop
  fi
)

# Mod+C can reopen chat only for an identified, still-running Twitch player.
if [ "${1:-}" = --chat-only ]; then
  kill -0 "$3" 2>/dev/null || exit 0
  SESSION_ID=$(cat "$SESSION_FILE" 2>/dev/null) || exit 0
  manage_chat start "$2"
  exit 0
fi

# --- 1. Setup & Force Icon Sync ---
if [ ! -f "$USERNAME_LIST" ]; then
  notify-send "Twitch Error" "Username list not found" -t 5000 -u critical
  exit 1
fi
mkdir -p "$IMAGE_CACHE"
mkdir -p "$PIXMAPS"
touch "$STATS_FILE"

# Profile-cache maintenance must not delay showing the picker.
(
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
  (
  # Never hold up the menu for avatar requests, or start duplicate fetches.
  exec 9>"$IMAGE_CACHE/.fetch.lock"
  flock -n 9 || exit 0
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
  ) </dev/null &
fi

) </dev/null &

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

# Read the background live check without delaying the picker for a request.
python3 - "$HOME/scripts" >>"$MENU_TMP" <<'PYMENU'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from stream_live_cache import menu
for service in ('Rumble', 'YouTube', 'Kick'):
    menu(Path.home()/'.cache'/(service.lower()+'-live.json'), service)
PYMENU

TOP5=$(sort -t"$(printf '\t')" -k1,1nr -k2,2 "$MENU_TMP" | awk -F'\t' '$1 + 0 > 0' | head -n 5)

CUSTOM_CHANNEL_URL=""
# An argument names a streamer to open directly, skipping the picker. Used by
# the go-live notification's Watch button, which already knows who you want.
if [ -n "${1:-}" ]; then
  CHOICE="$1"
else
# Display the friendly label, but return its hidden service-tagged identity.
# Free text stays distinguishable from selected rows (which contain a tab).
MENU_ORDERED=$(mktemp)
  {
    [ -n "$TOP5" ] && printf '%s\n' "$TOP5"
    sort -t"$(printf '\t')" -k2,2 "$MENU_TMP" | grep -vxF -f <(printf '%s\n' "$TOP5")
  } | awk -F'\t' 'NF >= 3' >"$MENU_ORDERED"
CHOICE_INPUT=$(
    awk -F'\t' -v p="$PIXMAPS" '
      NF >= 3 {
        split($3, w, " ")
        icon = (NF >= 4 && $4 != "") ? $4 : p "/" tolower(w[1]) ".png"
        label = $3
        sub(/ \(YouTube\)$/, "", label)
        sub(/ \(Rumble\)$/, "", label)
        sub(/ \(Kick\)$/, "", label)
        if (NF >= 5 && $5 != "") label = label " " $5
        printf "%s\t%s\000icon\x1f%s\n", label, $3, icon
      }' "$MENU_ORDERED" |
    python3 "$HOME/scripts/stream-picker-client.py"
)
CHOICE=""
if [[ "$CHOICE_INPUT" == *$'\t'* ]]; then
  CHOICE="${CHOICE_INPUT#*$'\t'}"
else
  # Explicit service prefixes work even when the channel is not in a list.
  # Bare usernames and Twitch links keep their original Twitch behavior.
  case "$CHOICE_INPUT" in
    [rR]/*|[yY]/*|[kK]/*)
      prefix="${CHOICE_INPUT:0:1}"
      custom="${CHOICE_INPUT:2}"
      custom="${custom#@}"
      custom="${custom%/}"
      case "${prefix,,}" in
        r) service=Rumble; base=https://rumble.com/c/; pattern='^[a-zA-Z0-9_-]+$' ;;
        y) service=YouTube; base=https://www.youtube.com/@; pattern='^[[:alnum:]_.-]+$' ;;
        k) service=Kick; base=https://kick.com/; pattern='^[a-zA-Z0-9_-]+$'; custom="${custom,,}" ;;
      esac
      if [[ "$custom" =~ $pattern ]]; then
        CHOICE="$custom ($service)"
        CUSTOM_CHANNEL_URL="$base$custom"
      fi
      ;;
    *)
      custom="${CHOICE_INPUT#https://}"
      custom="${custom#http://}"
      custom="${custom#www.}"
      custom="${custom#twitch.tv/}"
      custom="${custom#@}"
      custom="${custom%/}"
      if [[ "$custom" =~ ^[a-zA-Z0-9_]{1,25}$ ]]; then
        CHOICE="${custom,,}"
      fi
      ;;
  esac
  if [ -z "$CHOICE" ] && [ -n "$CHOICE_INPUT" ]; then
    notify-send -a "Streams" -t 4000 "Invalid stream username" \
      "Enter a Twitch username, r/name (Rumble), y/handle (YouTube), or k/name (Kick)."
  fi
fi
rm -f "$MENU_ORDERED"
fi
rm -f "$MENU_TMP"

if [ -z "$CHOICE" ]; then
  exit 0
fi

# Extract just the username
STREAMER_USERNAME=$(echo "$CHOICE" | awk '{print $1}')
STREAMER="$STREAMER_USERNAME"

# Claim the selection before resolving it; a slower old request must not
# replace a newer stream or display a stale failure notification.
echo "$SESSION_ID" >"$SESSION_FILE"

# Resolve non-Twitch broadcasts again on selection in case the cached live
# entry has since ended. They do not use Twitch credentials or Chatterino.
if [[ "$CHOICE" == *"(Rumble)" || "$CHOICE" == *"(YouTube)" || "$CHOICE" == *"(Kick)" ]]; then
  if [[ "$CHOICE" == *"(YouTube)" ]]; then
    SERVICE=YouTube
    CHANNEL_LIST="$HOME/scripts/youtube_live_channels.tsv"
    LIVE_HELPER="$HOME/scripts/youtube-live.py"
  elif [[ "$CHOICE" == *"(Kick)" ]]; then
    SERVICE=Kick
    CHANNEL_LIST="$HOME/scripts/kick_channels.tsv"
    LIVE_HELPER="$HOME/scripts/kick-live.py"
  else
    SERVICE=Rumble
    CHANNEL_LIST="$RUMBLE_LIST"
    LIVE_HELPER="$HOME/scripts/rumble-live.py"
  fi
  CHANNEL_URL="${CUSTOM_CHANNEL_URL:-}"
  if [ -z "$CHANNEL_URL" ]; then
    CHANNEL_URL=$(awk -v name="$STREAMER_USERNAME" '$1 == name {print $2; exit}' "$CHANNEL_LIST")
  fi
  (
    # The background live check already cached the avatar: show it immediately,
    # before waiting for the playback URL to resolve.
    IMG_PATH=$(python3 - "$CHANNEL_URL" <<'PYICON'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / 'scripts'))
from stream_profile import cache_avatar
print(cache_avatar(sys.argv[1], ''))
PYICON
)
    notify_loading "$IMG_PATH" "$STREAMER" &
    NOTIFY_ARGS=(-a "$SERVICE" -t 6000)
    [ -f "$IMG_PATH" ] && NOTIFY_ARGS+=(-i "$IMG_PATH")
    ERROR_FILE=$(mktemp)
    if ! LIVE=$(python3 "$LIVE_HELPER" "$CHANNEL_URL" 2>"$ERROR_FILE"); then
      if stream_session_current; then
        notify-send "${NOTIFY_ARGS[@]}" "$STREAMER — $SERVICE" "$(cat "$ERROR_FILE")"
      fi
      rm -f "$ERROR_FILE"
      exit 1
    fi
    rm -f "$ERROR_FILE"
    stream_session_current || exit 0
    LIVE_URL=$(jq -er '.url' <<<"$LIVE") || exit 1
    LIVE_TITLE=$(jq -r '.title' <<<"$LIVE")
    PLAYER_TITLE=$(python3 "$HOME/scripts/stream_menu_metadata.py" "$STREAMER" "$SERVICE" "$LIVE_TITLE")
    PLAYER_ARGS=()
    if [[ "$SERVICE" == YouTube ]]; then
      YTDL="$HOME/.local/bin/yt-dlp"
      [ -x "$YTDL" ] || YTDL=$(command -v yt-dlp)
      PLAYER_ARGS=("--script-opts=ytdl_hook-ytdl_path=$YTDL"
        '--ytdl-format=bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best')
    else
      PLAYER_ARGS=(--user-agent=Mozilla/5.0 "--referrer=https://${SERVICE,,}.com/")
    fi
    # Quality switching reads this JSON instead of evaluating stream titles.
    CONTEXT="$HOME/.cache/${SERVICE,,}-live-player.json"
    jq --arg service "$SERVICE" --arg channel "$CHANNEL_URL" '. + {service:$service, channel:$channel, quality:"best"}' <<<"$LIVE" >"$CONTEXT.tmp"
    mv "$CONTEXT.tmp" "$CONTEXT"
    stream_session_current || exit 0
    pkill mpv
    python3 "$HOME/scripts/media-chat.py" --close-youtube
    manage_chat stop &
    stream_session_current || exit 0
    play_live_stream --cache=yes --cache-secs=30 --demuxer-max-bytes=150MiB \
      --demuxer-max-back-bytes=100MiB --hwdec=auto \
      --input-ipc-server="/tmp/mpv-${SERVICE,,}-live-ipc" \
      "${PLAYER_ARGS[@]}" --force-media-title="$PLAYER_TITLE" "$LIVE_URL"
  ) &
  exit 0
fi
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

  # Claim this stream before killing the old mpv, so the previous instance's
  # cleanup knows it has been superseded. Chatterino is (re)started further
  # down, after the old mpv is gone.
  stream_session_current || exit 0

  IMG_PATH="$PIXMAPS/${STREAMER_USERNAME,,}.png"
  notify_loading "$IMG_PATH" "$STREAMER" &

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

  # Chat and URL resolution proceed independently. Leave the current player
  # intact until we know whether its window can be reused.
  manage_chat start "$STREAMER_USERNAME" &
  # Resolve the network URL while preparing local title/monitor settings.
  LOW_FILE=$(mktemp "${XDG_RUNTIME_DIR:-/tmp}/twitch-url.XXXXXX")
  python3 "$HOME/scripts/twitch-stream-url.py" "$STREAMER_USERNAME" >"$LOW_FILE" 2>/dev/null &
  RESOLVE_PID=$!
  PLAYER_TITLE=$(python3 "$HOME/scripts/stream_menu_metadata.py" "$STREAMER" Twitch)

  # Pillarbox only shows up on the 16:9 LG; on the 3:2 laptop panel
  # panscan=1.0 would crop ~14% off the sides. Apply only when docked.
  ASPECT_ARGS=()
  if hyprctl monitors -j 2>/dev/null | jq -e '.[] | select(.disabled == false and (.description | test("LG ULTRAGEAR"))) ' >/dev/null; then
    ASPECT_ARGS=(--panscan=1.0)
  fi

  wait "$RESOLVE_PID"
  LOW_URL=$(cat "$LOW_FILE")
  rm -f "$LOW_FILE"

  if [ -z "$LOW_URL" ]; then
    stream_session_current || exit 0
    pkill mpv
    streamlink "${SL_COMMON[@]}" --player mpv "$URL" best,720p,480p
    STREAM_RC=$?
    chat_stop_if_current
    exit $STREAM_RC
  fi

  # back-bytes feeds mpv-clip.sh, which dumps the last 30s out of this buffer;
  # 30s of 1080p60 is roughly 25MB, so the previous 50MiB was marginal.
  # force-media-title so the window and the clip filenames say who is streaming
  # rather than showing the HLS playlist token.
  stream_session_current || exit 0
  FIRST_FRAME=$(mktemp "${XDG_RUNTIME_DIR:-/tmp}/twitch-first-frame.XXXXXX")
  MPV_PID=$(python3 "$HOME/scripts/twitch-player-ipc.py" "$STREAMER_USERNAME" "$PLAYER_TITLE" "$LOW_URL" "$FIRST_FRAME" 2>/dev/null)
  REUSED_PLAYER=1
  if [ -z "$MPV_PID" ]; then
    REUSED_PLAYER=0
    pkill mpv
    rm -f "$MPV_SOCKET"
  TWITCH_STREAMER_USERNAME="$STREAMER_USERNAME" TWITCH_FIRST_FRAME="$FIRST_FRAME" mpv \
    --term-status-msg= \
    --script="$HOME/scripts/twitch-first-frame.lua" \
    --cache=yes \
    --cache-secs=30 \
    --demuxer-max-bytes=150MiB \
    --demuxer-max-back-bytes=100MiB \
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
    --force-media-title="$PLAYER_TITLE" \
    "$LOW_URL" &
  MPV_PID=$!
  fi

  (
    for i in $(seq 1 150); do
      stream_session_current && kill -0 "$MPV_PID" 2>/dev/null || exit 0
      [ -s "$FIRST_FRAME" ] && [ -S "$MPV_SOCKET" ] && break
      sleep 0.1
    done
    [ -s "$FIRST_FRAME" ] && [ -S "$MPV_SOCKET" ] || exit 1
    sleep 0.5
    BEST_URL=$(python3 "$HOME/scripts/twitch-stream-url.py" "$STREAMER_USERNAME" --best 2>/dev/null)
    if [ -n "$BEST_URL" ] && stream_session_current && kill -0 "$MPV_PID" 2>/dev/null; then
      IPC_CMD=$(jq -cn --arg url "$BEST_URL" '{"command": ["loadfile", $url, "replace"]}')
      echo "$IPC_CMD" | socat - "$MPV_SOCKET" >/dev/null 2>&1
    fi
  ) &

  if [ "$REUSED_PLAYER" = 1 ]; then
    python3 "$HOME/scripts/twitch-player-ipc.py" wait "$MPV_PID" "$SESSION_ID"
  else
    wait "$MPV_PID"
  fi
  rm -f "$FIRST_FRAME"

  # Stream is over (window closed, or killed): take the chat window with it.
  chat_stop_if_current
) &
