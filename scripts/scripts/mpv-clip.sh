#!/bin/bash
# Save the last N seconds of whatever mpv is playing. Bound to "c" in
# ~/.config/mpv/input.conf.
#
# The clip comes out of mpv's own demuxer back-buffer via the dump-cache
# command, so it is instant, needs no network, and cannot be affected by an
# expiring URL. The previous version re-downloaded the segment with yt-dlp from
# the HLS playlist URL, which needed browser cookies and a URL that expires
# within minutes.

set -u

CLIP_DIR="${CLIP_DIR:-$HOME/Videos/clips}"
CLIP_LENGTH="${CLIP_LENGTH:-30}"
SOCKETS=(/tmp/mpv-twitch-ipc /tmp/mpv-yt-ipc)

mkdir -p "$CLIP_DIR" || exit 1

# Filled in once the streamer is known; empty until then, which is fine since
# notify-send simply gets no -i.
NOTE_ICON=()
note() { notify-send -a "Clip" "${NOTE_ICON[@]}" "${@}"; }
ipc() { printf '%s\n' "$2" | timeout 3 socat - "$1" 2>/dev/null; }

# Pick a socket that actually ANSWERS, rather than one that merely exists.
# Nothing removes a unix socket when its process dies, so a stale
# /tmp/mpv-yt-ipc outlives the mpv that made it -- and the old [ -S ] test
# selected that dead socket in preference to the live Twitch one, which is why
# the clip key silently stopped working for three months.
SOCKET=""
for s in "${SOCKETS[@]}"; do
  [ -S "$s" ] || continue
  if ipc "$s" '{"command":["get_property","time-pos"]}' | jq -e '.error == "success"' >/dev/null 2>&1; then
    SOCKET="$s"
    break
  fi
done
[ -n "$SOCKET" ] || { note "Clip" "No running mpv"; exit 1; }

pos=$(ipc "$SOCKET" '{"command":["get_property","time-pos"]}' | jq -r '.data // empty')
[ -n "$pos" ] || { note "Clip" "Could not read the playback position"; exit 1; }

state=$(ipc "$SOCKET" '{"command":["get_property","demuxer-cache-state"]}')
# How far back the buffer actually reaches. It is bounded by
# demuxer-max-back-bytes, and it restarts from zero whenever the stream is
# reloaded -- twitch-launcher.sh does exactly that a few seconds in, when it
# swaps up to the best quality. Clamp rather than asking for data mpv threw
# away: dump-cache would otherwise write a clip that silently starts late.
range_start=$(jq -r '.data."seekable-ranges"[0].start // 0' <<<"$state" 2>/dev/null)
[ -n "$range_start" ] || range_start=0

read -r start got < <(awk -v p="$pos" -v l="$CLIP_LENGTH" -v rs="$range_start" \
  'BEGIN { s = p - l; if (s < rs) s = rs; if (s < 0) s = 0; printf "%.3f %.0f", s, p - s }')

if [ "${got:-0}" -lt 2 ]; then
  note -u normal "Clip" "Only ${got}s buffered -- nothing to save yet"
  exit 1
fi

# media-title is the stream's HLS playlist token unless something set a real
# one (twitch-launcher.sh passes --force-media-title). A token is long and has
# no spaces, so fall back rather than name the file after 50 characters of
# base64, which is what the older clips in this directory look like.
title=$(ipc "$SOCKET" '{"command":["get_property","media-title"]}' | jq -r '.data // empty')
name=$(printf '%s' "$title" | tr -dc '[:alnum:] _-' | sed 's/^ *//; s/ *$//' | head -c 50)
if [ -z "$name" ] || { [ "${#name}" -gt 24 ] && [[ "$name" != *" "* ]]; }; then
  name="stream"
fi

out="$CLIP_DIR/${name}_$(date +%Y%m%d_%H%M%S).mp4"

# The streamer's Twitch avatar on the notification, so a clip saved while you
# are looking at something else still says who it was of. Only for the Twitch
# socket: a YouTube media-title is not a twitch login and looking it up would
# be a pointless request that can only fail.
if [ "$SOCKET" = /tmp/mpv-twitch-ipc ] && [ "$name" != stream ]; then
  icon=$("$HOME/scripts/twitch-profile-pic.sh" "$name") || icon=""
  [ -n "$icon" ] && NOTE_ICON=(-i "$icon")
fi

# dump-cache picks the container from the extension. Twitch streams are h264 +
# aac, which MP4 takes as-is, so this is a straight remux with no re-encode and
# no post-processing step -- verified: 1920x1080 h264 + aac, 32s, in 30MB.
cmd=$(jq -cn --argjson s "$start" --argjson e "$pos" --arg f "$out" \
  '{"command":["dump-cache",$s,$e,$f]}')
resp=$(ipc "$SOCKET" "$cmd")

if jq -e '.error == "success"' >/dev/null 2>&1 <<<"$resp"; then
  size=$(du -h "$out" 2>/dev/null | cut -f1)
  note -t 4000 "Clip" "Saved ${got}s (${size:-?}) — $(basename "$out")"
else
  note -u critical "Clip" "mpv refused: $(jq -r '.error // "no response"' <<<"$resp" 2>/dev/null)"
  exit 1
fi
