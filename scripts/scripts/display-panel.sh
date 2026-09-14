#!/bin/bash
# Display panel for the waybar custom/display module.
#
# Same shape as wifi-panel.sh / battery-panel.sh / bluetooth-panel.sh: a
# swaync notification with action buttons. Scale is stepped with buttons
# rather than a slider -- notifications cannot host a slider, and the value
# space is discrete anyway (Hyprland rejects any scale whose logical size is
# not an integer).
#
# Scale changes go through display-scale.py, which writes the kanshi profile.
# Setting it with hyprctl looks like it works (prints "ok") but kanshi
# re-applies its own scale within about a second and silently reverts it.

TIMEOUT_MS=15000
STEP=10

bright_pct() { brightnessctl -m 2>/dev/null | awk -F, '{gsub("%","",$4); print $4}'; }
night_on() { pgrep -x hyprsunset >/dev/null 2>&1; }

# Waybar polls this for the icon + tooltip. Handled before the guard is
# sourced: polling must never contend for the panel's lock.
if [ "$1" = "--waybar" ]; then
  pct=$(bright_pct)
  if night_on; then night="on"; else night="off"; fi
  mon=$(hyprctl monitors -j 2>/dev/null |
    jq -r '[.[] | select(.disabled == false)]
           | map("\(.name) \(.width)x\(.height)@\(.refreshRate|floor)Hz")
           | join("\n")')
  jq -cn --arg t "$(printf '\U000F0379')" \
    --arg tip "$(printf 'Brightness %s%%\nNight light %s\n%s' "${pct:-?}" "$night" "$mon")" \
    '{text: $t, tooltip: $tip, class: (if "'"$night"'" == "on" then "night" else "day" end)}'
  exit 0
fi

# Single-instance guard: a second click closes the open panel rather
# than stacking another one. See panel-guard.sh.
source "$HOME/scripts/panel-guard.sh"
panel_guard display

pct=$(bright_pct)
if night_on; then night_state="on"; else night_state="off"; fi

cur=$("$HOME/scripts/display-scale.py" --current 2>/dev/null)
read -r prev next < <("$HOME/scripts/display-scale.py" --neighbours 2>/dev/null)

mons=$(hyprctl monitors -j 2>/dev/null |
  jq -r '[.[] | select(.disabled == false)]
         | map("\(.name)  \(.width)x\(.height)@\(.refreshRate|floor)Hz")
         | join("\n           ")')

body=$(printf '<tt>Output     %s\nScale      %sx\nBrightness %s%%\nNight      %s</tt>' \
  "${mons:-unknown}" "${cur:-?}" "${pct:-?}" "$night_state")

night_label="Night Light"
night_on && night_label="Night Light ✓"

scale_args=()
[ -n "$prev" ] && [ "$prev" != "-" ] && scale_args+=(-A "scaledown=Scale ${prev}x")
[ -n "$next" ] && [ "$next" != "-" ] && scale_args+=(-A "scaleup=Scale ${next}x")

action=$(panel_notify -a "Screen" -u low -t "$TIMEOUT_MS" \
  "Display" "$body" \
  -A "down=Brightness -${STEP}%" \
  -A "up=Brightness +${STEP}%" \
  "${scale_args[@]}" \
  -A "night=$night_label" \
  -A "relayout=Reload Layout")

case "$action" in
down)
  brightnessctl set "${STEP}%-" >/dev/null
  notify-send -a "Screen" -u low -t 1500 "Display" "Brightness $(bright_pct)%"
  ;;
up)
  brightnessctl set "+${STEP}%" >/dev/null
  notify-send -a "Screen" -u low -t 1500 "Display" "Brightness $(bright_pct)%"
  ;;
scaledown | scaleup)
  [ "$action" = "scaledown" ] && target="$prev" || target="$next"
  msg=$("$HOME/scripts/display-scale.py" --set "$target" 2>&1)
  if [ $? -eq 0 ]; then
    notify-send -a "Screen" -u low -t 2500 "Display" "$msg"
  else
    notify-send -a "Screen" -u normal -t 3500 "Display" "Scale failed: $msg"
  fi
  ;;
night)
  "$HOME/scripts/toggle-hyprsunset.sh"
  sleep 0.3
  if night_on; then st="on"; else st="off"; fi
  notify-send -a "Screen" -u low -t 2000 "Display" "Night light $st"
  ;;
relayout)
  kanshictl reload >/dev/null 2>&1 &&
    notify-send -a "Screen" -u low -t 2000 "Display" "Reloaded kanshi layout" ||
    notify-send -a "Screen" -u normal -t 3000 "Display" "kanshictl reload failed"
  ;;
esac
