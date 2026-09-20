#!/bin/bash
# Notify when a streamer you care about starts streaming.
#
# Driven by update-live-list.sh, which already refreshes the live list every 5
# minutes -- so going live is just the difference between this run's live set
# and the previous one. No extra polling and no extra API calls.
#
#   ~/scripts/twitch_notify.txt   who to notify for, one login per line, # comments
#   twitch-golive-notify.sh --list   show who is configured and who is live now
#
# Deliberately quiet in two situations:
#   * the very first run, when there is no previous set to compare against and
#     every live streamer would otherwise look like they just started;
#   * a repeat inside COOLDOWN, because a stream that drops and reconnects
#     leaves and re-enters the live set within minutes.

set -u

LIVE_LIST="${LIVE_LIST:-$HOME/scripts/twitch_usernames.txt}"
NOTIFY_LIST="${NOTIFY_LIST:-$HOME/scripts/twitch_notify.txt}"
STATE="${STATE:-$HOME/.cache/twitch_golive_seen}"
LAST="${LAST:-$HOME/.cache/twitch_golive_last}"
COOLDOWN="${COOLDOWN:-21600}"   # seconds; 6h

mkdir -p "$(dirname "$STATE")"
touch "$STATE" "$LAST"

# login -> the rest of the display line ("— Fortnite · 113k · 5h08m")
declare -A LIVE_DESC=()
if [ -r "$LIVE_LIST" ]; then
  while read -r name rest; do
    [ -n "${name:-}" ] || continue
    LIVE_DESC["${name,,}"]="$rest"
  done <"$LIVE_LIST"
fi

if [ "${1:-}" = "--list" ]; then
  printf '%-18s %-8s %s\n' STREAMER STATUS DETAIL
  while read -r line; do
    line=${line%%#*}; line=${line//[[:space:]]/}
    [ -n "$line" ] || continue
    if [ -n "${LIVE_DESC[${line,,}]:-}" ]; then
      printf '%-18s %-8s %s\n' "$line" LIVE "${LIVE_DESC[${line,,}]}"
    else
      printf '%-18s %-8s\n' "$line" offline
    fi
  done <"$NOTIFY_LIST"
  exit 0
fi

[ -r "$NOTIFY_LIST" ] || exit 0

# A missing or empty state file means we have never run: record and stay silent.
first_run=0
[ -s "$STATE" ] || first_run=1

now=$(date +%s)
declare -A WAS=()
while read -r l; do [ -n "${l:-}" ] && WAS["$l"]=1; done <"$STATE"

declare -A LAST_AT=()
while read -r l t; do [ -n "${l:-}" ] && LAST_AT["$l"]="${t:-0}"; done <"$LAST"

while read -r line; do
  line=${line%%#*}; line=${line//[[:space:]]/}
  [ -n "$line" ] || continue
  login="${line,,}"
  desc="${LIVE_DESC[$login]:-}"
  [ -n "$desc" ] || continue                 # not live
  [ -z "${WAS[$login]:-}" ] || continue      # was already live last run
  [ "$first_run" = 0 ] || continue
  prev="${LAST_AT[$login]:-0}"
  [ $((now - prev)) -ge "$COOLDOWN" ] || continue

  icon=$("$HOME/scripts/twitch-profile-pic.sh" "$login") || icon=""
  args=(-a "Twitch" -u normal -t 20000 -A "watch=Watch")
  [ -n "$icon" ] && args+=(-i "$icon")
  # Detached: notify-send with -A blocks until the action is clicked or the
  # notification times out, and this runs from cron behind the list refresh.
  (
    action=$(notify-send "${args[@]}" "$line is live" "${desc#— }" 2>/dev/null)
    [ "$action" = "watch" ] && setsid -f "$HOME/scripts/twitch-launcher.sh" "$line" >/dev/null 2>&1
  ) >/dev/null 2>&1 &
  LAST_AT[$login]=$now
done <"$NOTIFY_LIST"

# Persist: everyone live now (for the next diff), and the notify timestamps.
printf '%s\n' "${!LIVE_DESC[@]}" | sort >"$STATE"
: >"$LAST"
for k in "${!LAST_AT[@]}"; do printf '%s %s\n' "$k" "${LAST_AT[$k]}" >>"$LAST"; done
