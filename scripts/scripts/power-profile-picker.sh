#!/bin/bash

CURRENT=$(powerprofilesctl get)
PROFILES=(performance balanced power-saver)

LIST=""
for p in "${PROFILES[@]}"; do
  if [ "$p" = "$CURRENT" ]; then
    LIST+="● $p"$'\n'
  else
    LIST+="  $p"$'\n'
  fi
done

CHOICE=$(printf "%s" "$LIST" | fuzzel --dmenu --prompt="Power Profile: " --lines=3 --width=20)

if [ -n "$CHOICE" ]; then
  PROFILE=$(echo "$CHOICE" | sed -E 's/^[●[:space:]]+//')
  if [ "$PROFILE" != "$CURRENT" ]; then
    powerprofilesctl set "$PROFILE"
    notify-send "Power Profile" "Set to $PROFILE"
  fi
fi
