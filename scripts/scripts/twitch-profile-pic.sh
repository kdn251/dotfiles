#!/bin/bash
# Print the local path to a Twitch streamer's profile image, fetching and
# caching it on a miss. Prints nothing and exits non-zero when it cannot be
# had, so callers can just omit notify-send's -i rather than handle an error.
#
#   icon=$(~/scripts/twitch-profile-pic.sh shroud) && notify-send -i "$icon" ...
#
# Shares ~/.cache/twitch-profiles with twitch-launcher.sh, which fills the same
# files for the fuzzel picker: a streamer seen there is already warm here and
# vice versa. Fetching is still needed because the two scripts keep separate
# streamer lists, so the VOD downloader can hit a name the picker never showed.

set -u

CACHE="$HOME/.cache/twitch-profiles"
# Twitch's public web client id -- the anonymous one the site itself ships, the
# same value twitch-launcher.sh uses. Not a credential, nothing account-linked.
CLIENT_ID="kimne78kx3ncx6brgo4mv6wki5h1ko"

[ $# -ge 1 ] || exit 1
user=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
[ -n "$user" ] || exit 1
img="$CACHE/$user.png"

# -s rather than -f: a zero-byte file left by an interrupted fetch should be
# retried, not served as a broken icon forever.
if [ -s "$img" ]; then
  printf '%s' "$img"
  exit 0
fi

mkdir -p "$CACHE" || exit 1

url=$(curl -s --max-time 4 -H "Client-Id: $CLIENT_ID" \
  -X POST -d "{\"query\":\"query{user(login:\\\"$user\\\"){profileImageURL(width:70)}}\"}" \
  "https://gql.twitch.tv/gql" 2>/dev/null |
  jq -r '.data.user.profileImageURL // empty' 2>/dev/null)
[ -n "$url" ] || exit 1

tmp=$(mktemp "${TMPDIR:-/tmp}/twitch-pfp.XXXXXX") || exit 1
trap 'rm -f "$tmp" "$tmp.png"' EXIT

curl -s --max-time 5 -o "$tmp" "$url" || exit 1
[ -s "$tmp" ] || exit 1

# Twitch serves WebP as readily as PNG and notification daemons will not render
# it, so normalise through ffmpeg exactly as twitch-launcher.sh does.
ffmpeg -y -i "$tmp" -vframes 1 "$tmp.png" >/dev/null 2>&1 || exit 1
[ -s "$tmp.png" ] || exit 1

# Atomic install: several VOD downloads can start at once, and a half-written
# file would be picked up by the other one as a broken icon.
mv -f "$tmp.png" "$img" || exit 1
printf '%s' "$img"
