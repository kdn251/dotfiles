#!/bin/bash
# Turn Hyprland animations off when power actually matters, on otherwise.
#
# Context: animations were disabled wholesale in 85a03a7 to save battery, then
# re-enabled for window close effects. This keeps the effects without paying
# for them when the battery is genuinely low.
#
# Policy (tune THRESHOLD):
#   on AC                      -> animations ON
#   on battery, above THRESHOLD-> animations ON
#   on battery, at/below it    -> animations OFF
# Set THRESHOLD=100 for strict "off whenever on battery".
#
# Runtime only: `hyprctl keyword` does not touch hyprland.conf, so a
# `hyprctl reload` restores the configured default until the next power event.

THRESHOLD=25
AC="/sys/class/power_supply/ACAD/online"
BAT=$(echo /sys/class/power_supply/BAT* | awk '{print $1}')

on_ac() { [ "$(cat "$AC" 2>/dev/null)" = "1" ]; }
capacity() { cat "$BAT/capacity" 2>/dev/null || echo 100; }

want_animations() {
  on_ac && return 0
  [ "$(capacity)" -gt "$THRESHOLD" ]
}

apply() {
  local want cur
  if want_animations; then want=1; else want=0; fi
  cur=$(hyprctl getoption animations:enabled 2>/dev/null | awk '/^int:/{print $2}')
  [ "$cur" = "$want" ] && return 0
  hyprctl keyword animations:enabled "$want" >/dev/null 2>&1
  if [ "$want" = "0" ]; then
    notify-send -a "Power" -u low -t 3000 "Battery $(capacity)%" \
      "Animations off to save power" 2>/dev/null
  else
    notify-send -a "Power" -u low -t 2500 "Power" "Animations on" 2>/dev/null
  fi
}

case "$1" in
--watch)
  apply
  # UPower emits on AC connect/disconnect and battery level changes. udev would
  # need root; this works unprivileged from the user session.
  gdbus monitor --system --dest org.freedesktop.UPower 2>/dev/null |
    while read -r _; do
      # Coalesce bursts: a single plug event emits several signals.
      sleep 1
      while read -r -t 0.2 _; do :; done
      apply
    done
  ;;
--status)
  printf 'AC=%s battery=%s%% threshold=%s -> animations should be %s (currently %s)\n' \
    "$(cat "$AC" 2>/dev/null)" "$(capacity)" "$THRESHOLD" \
    "$(want_animations && echo on || echo off)" \
    "$(hyprctl getoption animations:enabled 2>/dev/null | awk '/^int:/{print $2}')"
  ;;
*) apply ;;
esac
