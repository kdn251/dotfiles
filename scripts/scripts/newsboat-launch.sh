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

# Keep the startup picture off the normal screen that ncurses reveals when
# it suspends for a browser or other external command.
cleanup() { printf '\e[?1049l\e[?25h'; }
trap cleanup EXIT INT TERM

# The sea is one long string sampled at a moving offset. Doubled so a slice
# taken near the end wraps around instead of coming back short.
WAVES='~^~~-~~^-~~~^~-~~^~~-~^~~~-~^~~-~~^~-~~~^~-~~^~~-~^~~~-~^~~-~~^~-~~^~~-~^~~~-'
WAVELEN=${#WAVES}
SEA="${WAVES}${WAVES}"

BOAT_W=16
BOAT_H=11

# Keep one rigid silhouette; only its vertical position changes.
BOAT_ROWS=(
  '                '
  '       |\       '
  '       | \      '
  '       |  \     '
  '       |   \    '
  '       |    \   '
  '       |_____\  '
  '       |        '
  ' ._____|______. '
  '  \          / '
  '   \________/  '
)
for ((i = 0; i < BOAT_H; i++)); do
  color=$WHITE
  [ "$i" -eq 7 ] && color=$DIM
  [ "$i" -ge 8 ] && color=$CYAN
  BOAT_ROWS[i]="${color}${BOAT_ROWS[i]}${RESET}"
done

# Bob the boat independently of the fixed waterline and caption.
draw() {
  local frame=$1
  local cols rows sea_w sea_left top i x wake wake_len heave phase
  local left visible surface

  cols=$(tput cols 2>/dev/null || echo 80)
  rows=$(tput lines 2>/dev/null || echo 24)
  sea_w=$((cols - 8))
  [ "$sea_w" -gt 64 ] && sea_w=64
  [ "$sea_w" -lt 24 ] && sea_w=24
  sea_left=$(((cols - sea_w) / 2))

  # Anchor the hull at the midpoint throughout the animation.
  x=$(((sea_w - BOAT_W) / 2))
  # Start just above the water, then lift the whole boat only one row.
  phase=$((frame % 32))
  heave=0
  if [ "$phase" -ge 6 ] && [ "$phase" -lt 22 ]; then heave=1; fi

  top=$(((rows - 18) / 2))
  [ "$top" -lt 1 ] && top=1

  printf '\e[2J\e[H'
  for ((i = 0; i < top + 2 - heave; i++)); do printf '\n'; done
  for ((i = 0; i < BOAT_H; i++)); do
    printf '%*s%s\n' "$((sea_left + x))" '' "${BOAT_ROWS[i]}"
  done

  # Restore the fixed water row after shifting only the boat upward.
  for ((i = 0; i < heave; i++)); do printf '\n'; done

  # Wake: a short trail of froth behind the hull, growing as speed builds.
  # Let the wake build gradually rather than snapping to full length.
  wake_len=$((frame / 3))
  [ "$wake_len" -gt 6 ] && wake_len=6
  wake=''
  # Keep the foam immediately behind the stern and within the water.
  left=$((x + 1 - wake_len))
  [ "$left" -lt 0 ] && left=0
  visible=$((x + 1))
  [ "$visible" -gt "$sea_w" ] && visible=$sea_w
  for ((i = left; i < visible; i++)); do wake="${wake}·"; done

  # Put the wake on the water itself, leaving no extra gap under the hull.
  surface=${SEA:$(((frame / 2) % WAVELEN)):$sea_w}
  printf '%*s%s%s%s%s%s%s%s\n' "$sea_left" '' \
    "$BLUE" "${surface:0:$left}" "$DIM" "$wake" \
    "$BLUE" "${surface:$visible}" "$RESET"
  printf '%*s%s%s%s\n' "$sea_left" '' "$DIM" "${SEA:$(((frame / 3 + 9) % WAVELEN)):$sea_w}" "$RESET"
  printf '\n%*s%snewsboat%s %s· setting sail%s\n' \
    "$((sea_left + (sea_w - 22) / 2))" '' "$WHITE" "$RESET" "$DIM" "$RESET"
}

printf '\e[?1049h\e[?25l'
if [ "${1:-}" = "--preview" ]; then
  f=0
  while [ "$f" -lt 140 ]; do
    draw "$f"
    f=$((f + 1))
    sleep 0.08
  done
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
  draw "$f"
  f=$((f + 1))
  # Checked between frames as well: waiting for the next frame boundary would
  # leave up to a whole frame of drawing on top of the interface.
  sleep 0.04
  raw_yet && break
  sleep 0.04
done

printf '\e[?25h'
wait "$NB_PID"
exit $?
