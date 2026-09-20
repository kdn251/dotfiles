#!/bin/bash
# Refresh the list of currently-live streamers that twitch-launcher.sh shows.
# Run from cron every 5 minutes.
#
# Output line format, one per live streamer:
#
#   jynxzi — Fortnite · 113k · 5h08m
#
# The first whitespace-separated field must stay the twitch login: the launcher
# takes it with awk '{print $1}' for the URL and lowercases it to find the
# cached avatar. Everything after it is display only.
#
# This used to run `streamlink --json` once per streamer, 8 at a time -- 157
# Python interpreter startups every 5 minutes, about a second each. Twitch's
# GraphQL endpoint answers for the whole list in ONE request (measured: 157
# users, 0.18s), and returns the viewer count and start time that streamlink's
# metadata does not carry.

set -u

MASTER_LIST="$HOME/scripts/twitch_master_list.txt"
LIVE_LIST="$HOME/scripts/twitch_usernames.txt"
LOG_FILE="/tmp/live_list_cron.log"
# Twitch's public web client id, as used by twitch-launcher.sh. Not a credential.
CLIENT_ID="kimne78kx3ncx6brgo4mv6wki5h1ko"

log() { echo "$(date): $*" >>"$LOG_FILE"; }

[ -f "$MASTER_LIST" ] || { log "ERROR: master list not found: $MASTER_LIST"; exit 1; }

# First field of each non-comment line, lowercased, as a JSON array.
logins=$(awk '!/^[[:space:]]*#/ && NF { print tolower($1) }' "$MASTER_LIST" |
  jq -R . | jq -s -c .)
[ "$logins" != "[]" ] || { log "ERROR: master list has no usable names"; exit 1; }

query=$(jq -n --argjson logins "$logins" '
  { query: ("query{users(logins:" + ($logins|tostring) +
            "){login displayName stream{ title viewersCount createdAt game{displayName} } }}") }')

response=$(curl -s --max-time 15 -H "Client-Id: $CLIENT_ID" \
  -H "Content-Type: application/json" -X POST -d "$query" \
  "https://gql.twitch.tv/gql" 2>/dev/null)

# Bail without touching the list on a failed or malformed response. The old
# version wrote an empty file whenever the check produced nothing, so a network
# blip emptied the picker until the next run.
if [ -z "$response" ] || ! jq -e '.data.users' >/dev/null 2>&1 <<<"$response"; then
  log "ERROR: GQL request failed or returned no users; keeping previous list"
  exit 1
fi

tmp="$LIVE_LIST.tmp"
jq -r '
  def human:
    if . >= 1000 then ((. / 100 | floor) / 10 | tostring) + "k" else tostring end;
  def uptime:
    (now - .) / 60 | floor
    | if . >= 60 then "\(. / 60 | floor)h\((. % 60) | tostring | ("0" + .)[-2:])m"
      else "\(.)m" end;
  # Long category names ("Grand Theft Auto V", "World of Warcraft") pushed the
  # uptime past the picker width and it truncated away. Cap the game instead so
  # the two numeric fields, which are fixed-width and the point of the line,
  # always survive.
  def game: if (. | length) > 13 then (.[0:12] + "\u2026") else . end;
  .data.users[]
  | select(. != null and .stream != null)
  # displayName only when it is the login with different capitalisation -- some
  # are non-ASCII and would not survive being used as a URL or a cache filename.
  | (if (.displayName | test("^[A-Za-z0-9_]+$")) then .displayName else .login end) as $name
  | "\($name) — \(.stream.game.displayName // "Unknown" | game) · \(.stream.viewersCount | human) · \(.stream.createdAt | fromdateiso8601 | uptime)"
' <<<"$response" | sort -f >"$tmp"

if [ -s "$tmp" ]; then
  mv "$tmp" "$LIVE_LIST"
  log "live list updated: $(wc -l <"$LIVE_LIST") live"
else
  # A genuinely empty result is possible (nobody live). Record it rather than
  # leaving a stale list around, but keep it distinguishable from an error.
  : >"$LIVE_LIST"
  rm -f "$tmp"
  log "live list updated: 0 live"
fi

# Going live is the difference between this live set and the previous one, so
# the notifier rides along here rather than polling on its own.
"$HOME/scripts/twitch-golive-notify.sh" >/dev/null 2>&1 || true
