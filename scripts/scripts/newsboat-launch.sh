#!/bin/bash
# Newsboat startup and refresh animation.
# --preview plays the animation without launching Newsboat.
# --render is an internal pipe protocol used by newsboat-session.py.

set -u

# Skip the animation when output is not a terminal, so cron and scripts that
# call newsboat are completely unaffected.
if [ "${1:-}" != "--render" ] && [ "${1:-}" != "--preview" ] && [ ! -t 1 ]; then
  exec newsboat "$@"
fi

# The session wrapper keeps Newsboat running on its own terminal while the
# loading screen is visible, and observes actual refresh completion events.
if [ "${1:-}" != "--preview" ] && [ "${1:-}" != "--render" ]; then
  exec python3 "$(dirname "$(readlink -f "$0")")/newsboat-session.py" "$@"
fi

CYAN=$'\e[38;5;80m'
BLUE=$'\e[38;5;38m'
DIM=$'\e[38;5;244m'
WHITE=$'\e[38;5;255m'
RED=$'\e[38;5;203m'
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

BOAT_W=32
BOAT_H=11

# Four smoke rows sit above a rigid, two-funnel steamship.
BOAT_ROWS=(
  '                                '
  '                                '
  '                                '
  '                                '
  '          __     __             '
  '         |##|   |##|            '
  '      ___|##|___|##|___         '
  '     |  [] [] [] []   |___      '
  '  ___|___________________|___  '
  '  \   o   o   o   o   o    /   '
  '   \______________________/    '
)

# Puffs rise out of each funnel, drift astern, then thin out.
smoke_rows() {
  local frame=$1 stack puff age row col glyph line
  for ((row = 0; row < 4; row++)); do BOAT_ROWS[row]='                                '; done
  for stack in 11 18; do
    for puff in 0 4 8; do
      age=$(((frame / 2 + puff + (stack == 18 ? 2 : 0)) % 12))
      row=$((3 - age / 3))
      col=$((stack + age / 3))
      glyph='.'
      [ "$age" -ge 3 ] && [ "$age" -lt 9 ] && glyph='o'
      line=${BOAT_ROWS[row]}
      BOAT_ROWS[row]="${line:0:col}${glyph}${line:col+1}"
    done
  done
}

# Bob the boat independently of the fixed waterline and caption.
draw() {
  local frame=$1 label=${2:-setting sail}
  local cols rows sea_w sea_left top i x wake wake_len heave phase
  local left visible surface caption_left color
  smoke_rows "$frame"

  cols=${3:-$(tput cols 2>/dev/null || echo 80)}
  rows=${4:-$(tput lines 2>/dev/null || echo 24)}
  sea_w=$((cols - 8))
  [ "$sea_w" -gt 64 ] && sea_w=64
  [ "$sea_w" -lt 32 ] && sea_w=32
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
    color=$WHITE
    [ "$i" -lt 4 ] && color=$DIM
    { [ "$i" -eq 4 ] || [ "$i" -eq 5 ] || [ "$i" -ge 9 ]; } && color=$RED
    printf '%*s%s%s%s\n' "$((sea_left + x))" '' "$color" "${BOAT_ROWS[i]}" "$RESET"
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
  caption_left=$(((cols - 10 - ${#label}) / 2))
  [ "$caption_left" -lt 0 ] && caption_left=0
  printf '\n%*s%snewsboat%s %s· %s%s\n' \
    "$caption_left" '' "$WHITE" "$RESET" "$DIM" "$label" "$RESET"

}

if [ "${1:-}" = "--render" ]; then
  trap - EXIT INT TERM
  while IFS=$'\t' read -r frame label cols rows; do
    draw "$frame" "$label" "$cols" "$rows"
    printf '\0'
  done
  exit 0
fi

printf '\e[?1049h\e[?25l'
f=0
while [ "$f" -lt 140 ]; do
  draw "$f"
  f=$((f + 1))
  sleep 0.08
done
