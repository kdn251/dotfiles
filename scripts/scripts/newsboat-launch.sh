#!/bin/bash
# Launch newsboat behind a short sailing animation.
#
# newsboat prints its own startup lines ("Loading configuration...done." and
# friends) while it opens the cache, which is what used to fill the screen.
# This draws a boat instead and hands over with exec, so newsboat still owns
# the terminal and behaves exactly as if it had been run directly, arguments
# included.
#
#   newsboat-launch.sh --preview   play the animation only, do not start newsboat

set -u

# Skip the animation when output is not a terminal, so cron and scripts that
# call newsboat are completely unaffected.
if [ ! -t 1 ]; then
  exec newsboat "$@"
fi

CYAN=$'\e[38;5;80m'
BLUE=$'\e[38;5;38m'
DIM=$'\e[38;5;244m'
WHITE=$'\e[38;5;255m'
RESET=$'\e[0m'

cleanup() { printf '\e[?25h'; }
trap cleanup EXIT INT TERM

# The sea is one long string sampled at a moving offset. Doubled so a slice
# taken near the end wraps around instead of coming back short.
WAVES='~^~~-~~^-~~~^~-~~^~~-~^~~~-~^~~-~~^~-~~~^~-~~^~~-~^~~~-~^~~-~~^~-~~^~~-~^~~~-'
WAVELEN=${#WAVES}
SEA="${WAVES}${WAVES}"

BOAT_W=15

# $1 = row, $2 = colour prefix applied to the hull rows
boat_line() {
  case "$1" in
  0) printf '%s      |\\%s'       "$WHITE" "$RESET" ;;
  1) printf '%s      | \\%s'      "$WHITE" "$RESET" ;;
  2) printf '%s      |  \\%s'     "$WHITE" "$RESET" ;;
  3) printf '%s      |   \\%s'    "$WHITE" "$RESET" ;;
  4) printf '%s      |    \\%s'   "$WHITE" "$RESET" ;;
  5) printf '%s      |_____\\%s'  "$WHITE" "$RESET" ;;
  6) printf '%s      |%s'         "$DIM"   "$RESET" ;;
  7) printf '%s._____|______.%s'  "$CYAN"  "$RESET" ;;
  8) printf '%s \\           /%s' "$CYAN"  "$RESET" ;;
  9) printf '%s  \\_________/%s'  "$CYAN"  "$RESET" ;;
  esac
}

# frame -> a whole scene. The boat travels left to right across the sea while
# the swell scrolls the other way, which is what sells forward motion; an
# earlier version only jittered it one column back and forth on the spot, which
# just looked like stuttering. The hull also rises a row every few frames so it
# rides the swell rather than sliding along a rail.
draw() {
  local frame=$1
  local cols rows sea_w sea_left top i x bob wake wake_len

  cols=$(tput cols 2>/dev/null || echo 80)
  rows=$(tput lines 2>/dev/null || echo 24)
  sea_w=$((cols - 8))
  [ "$sea_w" -gt 64 ] && sea_w=64
  [ "$sea_w" -lt 24 ] && sea_w=24
  sea_left=$(((cols - sea_w) / 2))

  # Travel from just inside the left of the sea to just short of the right.
  local span=$((sea_w - BOAT_W - 2))
  [ "$span" -lt 1 ] && span=1
  x=$((sea_left + 1 + frame * span / TOTAL_FRAMES))
  # Bob every third frame so it is a swell, not a vibration.
  bob=$(((frame / 3) % 2))

  top=$(((rows - 16) / 2))
  [ "$top" -lt 1 ] && top=1

  printf '\e[2J\e[H'
  for ((i = 0; i < top; i++)); do printf '\n'; done
  # A blank line above or below the boat is what makes the bob visible.
  [ "$bob" -eq 1 ] && printf '\n'
  for ((i = 0; i < 10; i++)); do
    printf '%*s' "$x" ''
    boat_line "$i"
    printf '\n'
  done
  [ "$bob" -eq 0 ] && printf '\n'

  # Wake: a short trail of froth behind the hull, growing as speed builds.
  wake_len=$((frame > 8 ? 8 : frame))
  wake=''
  for ((i = 0; i < wake_len; i++)); do wake="${wake}·"; done

  printf '%*s%s%s%s\n' "$sea_left" '' "$BLUE" "${SEA:$(((frame * 2) % WAVELEN)):$sea_w}" "$RESET"
  printf '%*s%s%s%s\n' "$((x > wake_len ? x - wake_len : 0))" '' "$DIM" "$wake" "$RESET"
  printf '%*s%s%s%s\n' "$sea_left" '' "$DIM" "${SEA:$(((frame * 3 + 9) % WAVELEN)):$sea_w}" "$RESET"
  printf '\n%*s%snewsboat%s %s· setting sail%s\n' \
    "$((sea_left + (sea_w - 22) / 2))" '' "$WHITE" "$RESET" "$DIM" "$RESET"
}

TOTAL_FRAMES=16

printf '\e[?25l'
if [ "${1:-}" = "--preview" ]; then
  for pass in 1 2 3; do
    for ((f = 0; f <= TOTAL_FRAMES; f++)); do draw "$f"; sleep 0.075; done
  done
  cleanup
  exit 0
fi

for ((f = 0; f <= TOTAL_FRAMES; f++)); do
  draw "$f"
  sleep 0.075
done
cleanup
printf '\e[2J\e[H'
exec newsboat "$@"
