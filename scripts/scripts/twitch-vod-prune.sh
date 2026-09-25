#!/bin/bash
# Enforce the Twitch VOD retention policy.
#
#   twitch-vod-prune.sh           dry run -- print what would go, delete nothing
#   twitch-vod-prune.sh --apply   actually delete
#
# Two kinds of file get removed:
#
#   aborted  a download that was cancelled or died. NOT detected by file size:
#            streamlink finalises the container even when it is killed, so these
#            are perfectly readable files that simply stop early -- measured at
#            10s to 3.5min against 7-9 HOUR real VODs. Duration is the honest
#            signal, and it separates the two by three orders of magnitude.
#   excess   anything beyond the newest KEEP per streamer.
#
# The downloader only ever deleted the single previous VOD id it had recorded,
# and only after a SUCCESSFUL download, so anything interrupted orphaned
# permanently: 44 files on disk against 8 archive entries, 440GB.
#
# Files belonging to a download that is running right now are never touched.

set -u

VOD_DIR="${VOD_DIR:-$HOME/Videos/newsboat/twitch-vods}"
KEEP="${KEEP:-2}"              # newest N per streamer
MIN_DURATION="${MIN_DURATION:-600}"   # seconds; below this a file is an aborted download

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

[ -d "$VOD_DIR" ] || { echo "no such directory: $VOD_DIR" >&2; exit 1; }

# --- files currently being written -------------------------------------------
# A running streamlink names its target with --output. Never prune those: the
# file is mid-download and will look tiny and aborted while perfectly healthy.
declare -A BUSY=()
for pid in /proc/[0-9]*; do
  pid=${pid#/proc/}
  [ -r "/proc/$pid/cmdline" ] || continue
  mapfile -d '' -t args <"/proc/$pid/cmdline" 2>/dev/null || continue
  [ "${#args[@]}" -gt 1 ] || continue
  hit=0
  for ((i = 0; i < ${#args[@]} && i < 3; i++)); do
    case "$(basename -- "${args[$i]}")" in
    streamlink*) hit=1; break ;;
    esac
  done
  [ "$hit" = 1 ] || continue
  for ((i = 0; i < ${#args[@]} - 1; i++)); do
    if [ "${args[$i]}" = "--output" ]; then
      BUSY["${args[$((i + 1))]}"]=1
      break
    fi
  done
done

# --- classify ----------------------------------------------------------------
# rows: keep|excess|aborted \t streamer \t vodid \t bytes \t duration \t path
rows=$(
  find "$VOD_DIR" -maxdepth 1 -type f -name '*.mp4' -print0 |
    while IFS= read -r -d '' f; do
      base=$(basename -- "$f"); base=${base%.mp4}
      # "<streamer> - <title> - <vodid>"; titles can contain " - " themselves,
      # so take the first and last fields rather than splitting on every dash.
      streamer=${base%% - *}
      vodid=${base##* - }
      bytes=$(stat -c%s -- "$f" 2>/dev/null || echo 0)
      dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 -- "$f" 2>/dev/null)
      dur=${dur%%.*}
      [ -n "$dur" ] || dur=0
      printf '%s\t%s\t%s\t%s\t%s\n' "$streamer" "$vodid" "$bytes" "$dur" "$f"
    done |
    # newest first within each streamer. Twitch VOD ids ascend, so the id is a
    # more reliable ordering than mtime, which a copy or a touch would disturb.
    sort -t"$(printf '\t')" -k1,1 -k2,2nr |
    awk -F'\t' -v keep="$KEEP" -v mindur="$MIN_DURATION" '
      { if ($1 != last) { n = 0; last = $1 }
        if ($4 + 0 < mindur) { verdict = "aborted" }
        else { n++; verdict = (n <= keep) ? "keep" : "excess" }
        printf "%s\t%s\n", verdict, $0 }'
)

# --- report ------------------------------------------------------------------
human() { awk -v b="$1" 'BEGIN{ if (b>1073741824) printf "%.1fG", b/1073741824; else printf "%.0fM", b/1048576 }'; }
hms()   { awk -v s="$1" 'BEGIN{ printf "%dh%02dm", s/3600, (s%3600)/60 }'; }

total_freed=0; n_del=0; n_keep=0; n_busy=0
printf '%-8s %-12s %7s %8s  %s\n' VERDICT STREAMER SIZE LENGTH FILE
printf '%s\n' "------------------------------------------------------------------------"
while IFS=$'\t' read -r verdict streamer vodid bytes dur path; do
  [ -n "${verdict:-}" ] || continue
  if [ -n "${BUSY[$path]:-}" ]; then
    verdict="BUSY"; n_busy=$((n_busy + 1))
  fi
  case "$verdict" in
  keep) n_keep=$((n_keep + 1)); continue ;;
  BUSY) ;;
  *) total_freed=$((total_freed + bytes)); n_del=$((n_del + 1)) ;;
  esac
  printf '%-8s %-12s %7s %8s  %s\n' \
    "$verdict" "${streamer:0:12}" "$(human "$bytes")" "$(hms "$dur")" "$(basename -- "$path" | cut -c1-46)"
done <<<"$rows"

printf '%s\n' "------------------------------------------------------------------------"
printf 'keeping %d, removing %d (%s), skipping %d in progress\n' \
  "$n_keep" "$n_del" "$(human "$total_freed")" "$n_busy"

[ "$APPLY" = 1 ] || { printf '\ndry run -- nothing deleted. Re-run with --apply to remove them.\n'; exit 0; }

while IFS=$'\t' read -r verdict streamer vodid bytes dur path; do
  [ -n "${verdict:-}" ] || continue
  [ "$verdict" = keep ] && continue
  [ -n "${BUSY[$path]:-}" ] && continue
  rm -f -- "$path" && echo "removed: $(basename -- "$path")"
done <<<"$rows"

# Refresh the local Newsboat VOD inventory after applied deletions.
python3 "$HOME/scripts/newsboat-vods.py" rebuild >/dev/null 2>&1 || true
