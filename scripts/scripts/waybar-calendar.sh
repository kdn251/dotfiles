#!/usr/bin/env bash
# Calendar popup for the waybar clock. Launched in a floating kitty by
# the clock module's on-click; closes on any keypress.

printf '\n'
cal -3
printf '\n  %s\n' "$(date '+%A, %B %-d %Y   %-I:%M %p')"
printf '\n  press any key to close '
read -rsn1
