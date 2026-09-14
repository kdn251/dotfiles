#!/bin/bash
# Battery panel for the waybar battery module's on-click.
#
# Same shape as wifi-panel.sh: stats rendered as a swaync notification with
# action buttons, since waybar tooltips are pango text and cannot hold buttons.
# The buttons mirror what Super+Shift+B (power-profile-picker.sh) offers.

TIMEOUT_MS=15000

# Single-instance guard: a second click closes the open panel rather
# than stacking another one. See panel-guard.sh.
source "$HOME/scripts/panel-guard.sh"
panel_guard battery

BAT=$(echo /sys/class/power_supply/BAT* | awk '{print $1}')
[ -d "$BAT" ] || { notify-send -a "Battery" -u low "Battery" "No battery found."; exit 1; }

read_bat() { cat "$BAT/$1" 2>/dev/null; }

status=$(read_bat status)
cap=$(read_bat capacity)
cycles=$(read_bat cycle_count)

# This machine reports charge_* + current_now/voltage_now rather than energy_*
# and power_now, so watts have to be derived.
cnow=$(read_bat charge_now)
cfull=$(read_bat charge_full)
cdesign=$(read_bat charge_full_design)
inow=$(read_bat current_now)
vnow=$(read_bat voltage_now)

watts="-"
if [ -n "$inow" ] && [ -n "$vnow" ] && [ "$inow" -gt 0 ] 2>/dev/null; then
  watts=$(awk -v i="$inow" -v v="$vnow" 'BEGIN{printf "%.1f W", (i/1e6)*(v/1e6)}')
fi

health="-"
if [ -n "$cfull" ] && [ -n "$cdesign" ] && [ "$cdesign" -gt 0 ] 2>/dev/null; then
  health=$(awk -v f="$cfull" -v d="$cdesign" 'BEGIN{printf "%.0f%% of design", 100*f/d}')
fi

# Time remaining: to empty when discharging, to full when charging.
remaining="-"
if [ -n "$inow" ] && [ "$inow" -gt 0 ] 2>/dev/null; then
  case "$status" in
  Discharging)
    remaining=$(awk -v c="$cnow" -v i="$inow" \
      'BEGIN{h=c/i; printf "%dh %02dm left", int(h), int((h-int(h))*60)}')
    ;;
  Charging)
    remaining=$(awk -v c="$cnow" -v f="$cfull" -v i="$inow" \
      'BEGIN{h=(f-c)/i; printf "%dh %02dm to full", int(h), int((h-int(h))*60)}')
    ;;
  Full) remaining="Fully charged" ;;
  esac
fi

current_profile=$(powerprofilesctl get 2>/dev/null || echo "unknown")

body=$(printf '<tt>Charge   <b>%s%%</b>  (%s)\nTime     %s\nDraw     %s\nHealth   %s\nCycles   %s\nProfile  %s</tt>' \
  "$cap" "$status" "$remaining" "$watts" "$health" "${cycles:--}" "$current_profile")

# Mark the active profile so the buttons show current state
mark() { [ "$1" = "$current_profile" ] && printf ' ✓'; }

# No -i icon: the themed battery glyph is large and crowds the stats, and
# the wifi panel renders without one, so this keeps the two consistent.
action=$(panel_notify -a "Battery" -u low -t "$TIMEOUT_MS" \
  "Battery" "$body" \
  -A "performance=Performance$(mark performance)" \
  -A "balanced=Balanced$(mark balanced)" \
  -A "power-saver=Power Saver$(mark power-saver)")

case "$action" in
performance | balanced | power-saver)
  [ "$action" = "$current_profile" ] && exit 0
  powerprofilesctl set "$action" || exit 1
  # PPD 0.30 leaves cores capped at 400 MHz after leaving power-saver; the
  # same workaround power-profile-picker.sh uses.
  if [ "$action" != "power-saver" ]; then
    sudo -n /usr/local/bin/reset-cpu-freq
  fi
  notify-send -a "Battery" -u low -t 2500 "Power Profile" "Set to $action"
  ;;
esac
