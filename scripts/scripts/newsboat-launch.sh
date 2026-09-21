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
  local cols rows sea_w sea_left top i x wake wake_len

  cols=$(tput cols 2>/dev/null || echo 80)
  rows=$(tput lines 2>/dev/null || echo 24)
  sea_w=$((cols - 8))
  [ "$sea_w" -gt 64 ] && sea_w=64
  [ "$sea_w" -lt 24 ] && sea_w=24
  sea_left=$(((cols - sea_w) / 2))

  # Drift: one column every other frame, about seven columns a second. Fast
  # enough to read as sailing, slow enough to be calm -- it used to cross the
  # whole sea in under a second, which looked frantic.
  local span=$((sea_w - BOAT_W - 2))
  [ "$span" -lt 1 ] && span=1
  x=$((sea_left + 1 + (frame / 2) % (span + 1)))
  # No vertical movement at all. A terminal can only shift text by whole rows,
  # and even one row a second read as hopping rather than bobbing, so the boat
  # holds a fixed waterline and the drift, wake and scrolling swell carry the
  # motion instead.

  top=$(((rows - 16) / 2))
  [ "$top" -lt 1 ] && top=1

  printf '\e[2J\e[H'
  for ((i = 0; i < top; i++)); do printf '\n'; done
  for ((i = 0; i < 10; i++)); do
    printf '%*s' "$x" ''
    boat_line "$i"
    printf '\n'
  done
  printf '\n'

  # Wake: a short trail of froth behind the hull, growing as speed builds.
  # Wake builds gradually with the drift rather than snapping to full length.
  wake_len=$((frame / 3))
  [ "$wake_len" -gt 6 ] && wake_len=6
  wake=''
  for ((i = 0; i < wake_len; i++)); do wake="${wake}·"; done

  printf '%*s%s%s%s\n' "$sea_left" '' "$BLUE" "${SEA:$(((frame / 2) % WAVELEN)):$sea_w}" "$RESET"
  printf '%*s%s%s%s\n' "$((x > wake_len ? x - wake_len : 0))" '' "$DIM" "$wake" "$RESET"
  printf '%*s%s%s%s\n' "$sea_left" '' "$DIM" "${SEA:$(((frame / 3 + 9) % WAVELEN)):$sea_w}" "$RESET"
  printf '\n%*s%snewsboat%s %s· setting sail%s\n' \
    "$((sea_left + (sea_w - 22) / 2))" '' "$WHITE" "$RESET" "$DIM" "$RESET"
}

TOTAL_FRAMES=120

printf '\e[?25l'
if [ "${1:-}" = "--preview" ]; then
  f=0
  while [ "$f" -lt 140 ]; do
    draw "$((f % (TOTAL_FRAMES + 1)))"
    f=$((f + 1))
    sleep 0.08
  done
  cleanup
  exit 0
fi

# Start newsboat now and keep sailing while it opens the cache, rather than
# finishing the animation first and leaving a frozen frame on screen for the
# second or so that takes.
#
# -q suppresses its six startup lines ("Starting Newsboat r2.44...", "Loading
# articles from cache...done." and the rest), which otherwise printed over the
# boat. With those gone it loads in complete silence, so the animation has the
# terminal to itself until the interface appears.
#
# This is a background job only in the sense of &: job control is off in a
# script, so newsboat stays in this process group and can still read the
# keyboard. Without that it would take SIGTTIN on its first keypress.
# </dev/tty is essential: with job control off, bash points a background job's
# stdin at /dev/null, so newsboat would come up looking perfectly normal and
# then ignore every keypress -- including q.
newsboat -q "$@" </dev/tty &
NB_PID=$!

# ncurses puts the terminal into raw mode at the very moment it paints the
# interface -- measured at 1.22s, with the first byte of output in the same
# poll. That is the cue to stop drawing: one frame later and this would be
# scribbling over the interface, since escape sequences act on whichever screen
# buffer is current.
raw_yet() {
  local lflags
  lflags=$(stty -a </dev/tty 2>/dev/null) || return 1
  case "$lflags" in
  *-icanon*) return 0 ;;
  *) return 1 ;;
  esac
}

f=0
while kill -0 "$NB_PID" 2>/dev/null; do
  raw_yet && break
  draw "$((f % (TOTAL_FRAMES + 1)))"
  f=$((f + 1))
  # Checked between frames as well: waiting for the next frame boundary would
  # leave up to a whole frame of drawing on top of the interface.
  sleep 0.04
  raw_yet && break
  sleep 0.04
done

cleanup
wait "$NB_PID"
exit $?
