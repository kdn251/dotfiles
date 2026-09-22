#!/usr/bin/env bash
# Charge-level icon and percentage for Hyprlock, with a charging indicator.
for bat in /sys/class/power_supply/BAT*; do
    [[ -r "$bat/capacity" && -r "$bat/status" ]] || continue
    cap=$(<"$bat/capacity")
    status=$(<"$bat/status")
    [[ $cap =~ ^[0-9]+$ ]] || continue
    (( cap > 100 )) && cap=100
    icons=(󰂎 󰁺 󰁻 󰁼 󰁽 󰁾 󰁿 󰂀 󰂁 󰂂 󰁹)
    icon=${icons[$((cap / 10))]}
    charging=""
    [[ $status == Charging ]] && charging=" 󱐋"
    printf '%s %s%%%s\n' "$icon" "$cap" "$charging"
    exit 0
done
