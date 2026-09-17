#!/bin/bash

CURRENT=$(powerprofilesctl get)
PROFILES=(performance balanced power-saver)
ICON_DIR="$(dirname "$(readlink -f "$0")")/assets/power-profiles"
declare -A LABELS=(
  [performance]="Performance"
  [balanced]="Balanced"
  [power-saver]="Power Saver"
)

# Fuzzel uses the same image metadata as the Twitch profile-picture menu.
# Stream directly: shell variables cannot preserve the NUL before icon metadata.
CHOICE=$(
  for p in "${PROFILES[@]}"; do
    suffix=""
    [ "$p" = "$CURRENT" ] && suffix="  ✓"
    printf '%s%s\0icon\x1f%s/%s.svg\n' "${LABELS[$p]}" "$suffix" "$ICON_DIR" "$p"
  done | fuzzel --dmenu --prompt="Power ❯ " --lines=3 --width=24 --line-height=40 --text-color=ffffffff
)

case "$CHOICE" in
  Performance*) PROFILE=performance ;;
  Balanced*) PROFILE=balanced ;;
  "Power Saver"*) PROFILE=power-saver ;;
  *) exit 0 ;;
esac

if [ -n "$PROFILE" ]; then
  if [ "$PROFILE" != "$CURRENT" ]; then
    powerprofilesctl set "$PROFILE"
    # Workaround: PPD 0.30 leaves cores capped at 400 MHz after exiting
    # power-saver. Reset scaling_max_freq when switching to a non-saver profile.
    if [ "$PROFILE" != "power-saver" ]; then
      sudo -n /usr/local/bin/reset-cpu-freq
    fi
    notify-send "Power Profile" "Set to $PROFILE"
  fi
fi
