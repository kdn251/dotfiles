#!/bin/bash
# Print the local path to a YouTube channel's avatar, fetching and caching it on
# a miss. Prints nothing and exits non-zero when it cannot be had, so callers can
# just omit notify-send's -i.
#
#   icon=$(~/scripts/yt-channel-pic.sh UCMwJJL5FJFuTRT55ksbQ4GQ)
#
# The avatar is not part of a video's metadata, so it is scraped from the channel
# page: yt-dlp would have to list the channel to reach it, which is far slower
# than one request for the page (measured 0.24s). Mirrors twitch-profile-pic.sh.

set -u

CACHE="$HOME/.cache/yt-channel-avatars"

[ $# -ge 1 ] || exit 1
id="$1"
# Accept a bare id or any channel URL.
case "$id" in
*youtube.com/*) id=${id##*/} ;;
esac
[ -n "$id" ] || exit 1

img="$CACHE/$id.png"
# -s not -f: a zero-byte file from an interrupted fetch should be retried.
if [ -s "$img" ]; then
  printf '%s' "$img"
  exit 0
fi

mkdir -p "$CACHE" || exit 1

case "$id" in
UC*) url="https://www.youtube.com/channel/$id" ;;
*) url="https://www.youtube.com/@$id" ;;
esac

# The page embeds its JSON payload inline; the first "avatar" thumbnail is the
# channel picture.
pic=$(curl -s --max-time 8 -H 'Accept-Language: en-US' "$url" 2>/dev/null |
  grep -oP '"avatar":\{"thumbnails":\[\{"url":"\K[^"]+' | head -1)
[ -n "$pic" ] || exit 1

tmp=$(mktemp "${TMPDIR:-/tmp}/yt-chan.XXXXXX") || exit 1
trap 'rm -f "$tmp" "$tmp.png"' EXIT

curl -s --max-time 8 -o "$tmp" "$pic" || exit 1
[ -s "$tmp" ] || exit 1

# YouTube serves WebP here as often as JPEG, and notification daemons will not
# render it. Downscale while converting: the source is 900px and the popup shows
# it at about 64.
ffmpeg -y -i "$tmp" -vf scale=128:-1 -vframes 1 "$tmp.png" >/dev/null 2>&1 || exit 1
[ -s "$tmp.png" ] || exit 1

mv -f "$tmp.png" "$img" || exit 1
printf '%s' "$img"
