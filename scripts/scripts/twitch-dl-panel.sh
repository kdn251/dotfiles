#!/bin/bash
# Twitch VOD download monitor for waybar (custom/twitch_dl).
#
# Shows only while a VOD download is running; cron kicks the downloader off at
# 18/20/22. Click for a panel with the streamer's profile picture, the VOD
# title and progress, plus a cancel button per download.
#
# Active downloads are discovered from streamlink's own argv rather than from
# any state file, so ~/scripts/twitch-vod-downloader.sh needs no changes and
# this keeps working if that script is edited. /proc/<pid>/cmdline is read
# NUL-separated on purpose: the --output path contains spaces, so a
# space-joined `pgrep -a` line cannot be parsed unambiguously.
#
# The path is built by the downloader as:
#   $TWITCH_VOD_DIR/${streamer} - ${SAFE_TITLE} - ${VOD_ID}.mp4

TIMEOUT_MS=20000
PROFILE_CACHE="$HOME/.cache/twitch-profiles"
DL_ICON=$(printf '\U000F01DA')

human_size() {
  local b=${1:-0}
  awk -v b="$b" 'BEGIN{
    if (b >= 1073741824) printf "%.1f GB", b/1073741824;
    else if (b >= 1048576) printf "%.0f MB", b/1048576;
    else printf "%.0f KB", b/1024;
  }'
}

# pid \t streamer \t title \t vodid \t path
active_downloads() {
  local pid args out i base hit
  for pid in /proc/[0-9]*; do
    pid=${pid#/proc/}
    [ -r "/proc/$pid/cmdline" ] || continue
    mapfile -d '' -t args <"/proc/$pid/cmdline" 2>/dev/null || continue
    [ "${#args[@]}" -gt 1 ] || continue
    # streamlink is a Python script (#!/usr/bin/python), so a real download's
    # argv[0] is the interpreter and "streamlink" lands in argv[1]. Check the
    # first few args rather than argv[0] alone.
    local hit=0
    for ((i = 0; i < ${#args[@]} && i < 3; i++)); do
      case "$(basename -- "${args[$i]}")" in
      streamlink*)
        hit=1
        break
        ;;
      esac
    done
    [ "$hit" = 1 ] || continue
    out=""
    for ((i = 0; i < ${#args[@]} - 1; i++)); do
      if [ "${args[$i]}" = "--output" ]; then
        out="${args[$((i + 1))]}"
        break
      fi
    done
    [ -n "$out" ] || continue
    base=$(basename -- "$out")
    base=${base%.mp4}
    # "streamer - title - vodid"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "$pid" "${base%% - *}" "$(t=${base#* - }; echo "${t% - *}")" "${base##* - }" "$out"
  done
}

profile_pic() {
  local p="$PROFILE_CACHE/$(echo "$1" | tr '[:upper:]' '[:lower:]').png"
  [ -f "$p" ] && printf '%s' "$p"
}

# --- waybar feeder -------------------------------------------------------
# Handled before the guard is sourced: polling must not contend for the lock.
if [ "$1" = "--waybar" ]; then
  rows=$(active_downloads)
  if [ -z "$rows" ]; then
    # Empty text + hide-empty-text means the module disappears entirely.
    echo '{"text":""}'
    exit 0
  fi
  n=$(printf '%s\n' "$rows" | wc -l)
  tip=""
  total=0
  while IFS=$'\t' read -r pid streamer title vodid path; do
    [ -n "$pid" ] || continue
    sz=$(stat -c %s "$path" 2>/dev/null || echo 0)
    total=$((total + sz))
    tip+=$(printf '%s  %s\n%s\n' "$streamer" "$(human_size "$sz")" "$title")
    tip+=$'\n'
  done <<<"$rows"
  # Running total across every active download, so hovering answers "how much
  # has come down so far" without opening the panel.
  tip+=$(printf '\nDownloaded  %s' "$(human_size "$total")")
  text="$DL_ICON"
  [ "$n" -gt 1 ] && text="$DL_ICON $n"
  jq -cn --arg t "$text" --arg tip "${tip%$'\n'}" \
    '{text: $t, tooltip: $tip, class: "downloading"}'
  exit 0
fi

# --- cancel --------------------------------------------------------------
if [ "$1" = "--cancel" ]; then
  pid="$2"
  path="$3"
  name="$4"
  if kill "$pid" 2>/dev/null; then
    sleep 0.5
    kill -9 "$pid" 2>/dev/null
    # Remove the partial file; without this the next run may treat a truncated
    # mp4 as a finished download.
    [ -n "$path" ] && [ -f "$path" ] && rm -f "$path"
    notify-send -a "VOD" -u low -t 3000 "VOD Download" "Cancelled $name"
  else
    notify-send -a "VOD" -u normal -t 3000 "VOD Download" "Could not cancel $name (already finished?)"
  fi
  exit 0
fi

# --- panel ---------------------------------------------------------------
# Single-instance guard: a second click closes the open panel rather
# than stacking another one. See panel-guard.sh.
source "$HOME/scripts/panel-guard.sh"
panel_guard twitchdl

rows=$(active_downloads)
if [ -z "$rows" ]; then
  notify-send -a "VOD" -u low -t 3000 "VOD Download" "No downloads in progress."
  exit 0
fi

body=""
args=()
icon=""
idx=0
while IFS=$'\t' read -r pid streamer title vodid path; do
  [ -n "$pid" ] || continue
  sz=$(stat -c %s "$path" 2>/dev/null || echo 0)
  [ -z "$icon" ] && icon=$(profile_pic "$streamer")
  [ -n "$body" ] && body+=$'\n'
  body+=$(printf '<b>%s</b>  ·  %s\n%s' "$streamer" "$(human_size "$sz")" "$title")
  args+=(-A "c${idx}=✕ $streamer")
  eval "CPID_$idx=\$pid; CPATH_$idx=\$path; CNAME_$idx=\$streamer"
  idx=$((idx + 1))
done <<<"$rows"

notify_args=(-a "VOD" -u low -t "$TIMEOUT_MS")
[ -n "$icon" ] && notify_args+=(-i "$icon")

action=$(panel_notify "${notify_args[@]}" "Downloading VOD" "$body" "${args[@]}")

case "$action" in
c[0-9]*)
  i="${action#c}"
  eval "p=\$CPID_$i; f=\$CPATH_$i; n=\$CNAME_$i"
  "$0" --cancel "$p" "$f" "$n"
  ;;
esac
