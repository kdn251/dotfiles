#!/usr/bin/env bash
# Battery icon + percentage for hyprlock (Nerd Font glyphs)
bat=/sys/class/power_supply/BAT1
[ -d "$bat" ] || bat=$(ls -d /sys/class/power_supply/BAT* 2>/dev/null | head -1)
[ -d "$bat" ] || { echo ""; exit 0; }
cap=$(<"$bat/capacity"); status=$(<"$bat/status")
if [[ $status == Charging || $status == Full ]]; then
    icon="󰂄"
else
    icons=(󰁺 󰁻 󰁼 󰁽 󰁾 󰁿 󰂀 󰂁 󰂂 󰁹)
    idx=$(( cap / 10 )); (( idx > 9 )) && idx=9
    icon=${icons[$idx]}
fi
echo "$icon $cap%"
