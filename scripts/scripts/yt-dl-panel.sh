#!/bin/bash
# Panel for the yt-dlp download modules (custom/yt-download and
# custom/miniflux_download). Both are yt-dlp, so one panel covers them.
#
# Unlike streamlink, yt-dlp is invoked with an -o TEMPLATE ("%(title)s.%(ext)s")
# rather than a resolved path, so the filename cannot be read from argv. The
# in-progress file is found instead: yt-dlp writes "<name>.<ext>.part" while
# downloading, which gives both the title and live progress.

TIMEOUT_MS=20000
SEARCH_DIRS=(
  "$HOME/Videos/downloads"
  "$HOME/Videos/newsboat"
)

human_size() {
  awk -v b="${1:-0}" 'BEGIN{
    if (b >= 1073741824) printf "%.1f GB", b/1073741824;
    else if (b >= 1048576) printf "%.0f MB", b/1048576;
    else printf "%.0f KB", b/1024;
  }'
}

# pid of each running yt-dlp
ytdlp_pids() {
  local pid args i
  for pid in /proc/[0-9]*; do
    pid=${pid#/proc/}
    [ -r "/proc/$pid/cmdline" ] || continue
    mapfile -d '' -t args <"/proc/$pid/cmdline" 2>/dev/null || continue
    [ "${#args[@]}" -gt 1 ] || continue
    # yt-dlp is a Python script too, so check the first few args, not argv[0]
    for ((i = 0; i < ${#args[@]} && i < 3; i++)); do
      case "$(basename -- "${args[$i]}")" in
      yt-dlp*)
        echo "$pid"
        break
        ;;
      esac
    done
  done
}

# Partial files, newest first: "<size>\t<path>"
part_files() {
  local d
  for d in "${SEARCH_DIRS[@]}"; do
    [ -d "$d" ] || continue
    find "$d" -type f -name '*.part' -printf '%T@\t%s\t%p\n' 2>/dev/null
  done | sort -rn | cut -f2-
}

if [ "$1" = "--waybar" ]; then
  n=$(ytdlp_pids | wc -l)
  [ "$n" -eq 0 ] && { echo '{"text":""}'; exit 0; }
  tip=""
  total=0
  while IFS=$'\t' read -r sz path; do
    [ -n "$path" ] || continue
    total=$((total + sz))
    tip+=$(printf '%s  %s\n' "$(basename -- "${path%.part}")" "$(human_size "$sz")")
    tip+=$'\n'
  done < <(part_files)
  [ -z "$tip" ] && tip="yt-dlp running"
  tip+=$(printf '\nDownloaded  %s' "$(human_size "$total")")
  jq -cn --arg t "$(printf '\U000F01DA')" --arg tip "${tip%$'\n'}" \
    '{text: $t, tooltip: $tip, class: "downloading"}'
  exit 0
fi

if [ "$1" = "--cancel" ]; then
  pid="$2"
  path="$3"
  name="$4"
  kill "$pid" 2>/dev/null
  sleep 0.5
  kill -9 "$pid" 2>/dev/null
  # Remove the partial so a later run does not resume a half file unexpectedly
  [ -n "$path" ] && [ -f "$path" ] && rm -f "$path"
  notify-send -a "YT" -u low -t 3000 "Download" "Cancelled ${name:-download}"
  exit 0
fi

# Single-instance guard: a second click closes the open panel rather
# than stacking another one. See panel-guard.sh.
source "$HOME/scripts/panel-guard.sh"
panel_guard ytdl

mapfile -t pids < <(ytdlp_pids)
if [ "${#pids[@]}" -eq 0 ]; then
  notify-send -a "YT" -u low -t 3000 "Download" "No downloads in progress."
  exit 0
fi

body=""
args=()
idx=0
while IFS=$'\t' read -r sz path; do
  [ -n "$path" ] || continue
  name=$(basename -- "${path%.part}")
  [ -n "$body" ] && body+=$'\n'
  body+=$(printf '<b>%s</b>\n%s' "${name:0:60}" "$(human_size "$sz")")
  # Pair each partial with a yt-dlp pid; they are started one per download.
  p="${pids[$idx]:-${pids[0]}}"
  args+=(-A "c${idx}=✕ ${name:0:18}")
  eval "CPID_$idx=\$p; CPATH_$idx=\$path; CNAME_$idx=\$name"
  idx=$((idx + 1))
done < <(part_files)

if [ "$idx" -eq 0 ]; then
  body="yt-dlp is running but no .part file was found yet."
  args=(-A "c0=✕ Cancel")
  eval "CPID_0=\${pids[0]}; CPATH_0=; CNAME_0=download"
fi

action=$(panel_notify -a "YT" -u low -t "$TIMEOUT_MS" "Downloading" "$body" "${args[@]}")

case "$action" in
c[0-9]*)
  i="${action#c}"
  eval "p=\$CPID_$i; f=\$CPATH_$i; n=\$CNAME_$i"
  "$0" --cancel "$p" "$f" "$n"
  ;;
esac
