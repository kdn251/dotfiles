#!/bin/bash

CURRENT=$(powerprofilesctl get)
PROFILES=(performance balanced power-saver)
declare -A GLYPHS=(
  [performance]=$'\xef\x83\xa7'
  [balanced]=$'\xef\x89\x8e'
  ["power-saver"]=$'\xef\x81\xac'
)
declare -A PADS=(
  [performance]="  "
  [balanced]="   "
  ["power-saver"]="  "
)

LIST=""
for p in "${PROFILES[@]}"; do
  suffix=""
  [ "$p" = "$CURRENT" ] && suffix="  ✓"
  LIST+="${GLYPHS[$p]}${PADS[$p]}${p}${suffix}"$'\n'
done

CHOICE=$(printf "%s" "$LIST" | fuzzel --dmenu --prompt="❯ 󰂄 " --lines=3 --width=20 --text-color=ffffffff)

if [ -n "$CHOICE" ]; then
  PROFILE=$(echo "$CHOICE" | awk '{print $2}')
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
