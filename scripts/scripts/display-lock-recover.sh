#!/usr/bin/env bash
# Recover a docked resume that left the machine unusable.
#
# Entry points:
#   - hypridle's after_sleep_cmd, so it runs automatically on every wake
#   - Alt+Ctrl+K, bound with bindl so the key still reaches Hyprland while the
#     session is locked
#
# Two failures this repairs, both only seen while docked to the TS4:
#   1. The dock does not survive suspend ("0:3: lost during suspend",
#      "failed to reach state TB_PORT_UP"), so DP-1 never comes back. kanshi's
#      docked profile has eDP-1 disabled, and the phantom DP-1 head Hyprland
#      keeps can hold it in that profile, leaving no usable output at all.
#   2. hyprlock dies during the output churn (RASSERT at hyprlock.cpp:414) and
#      Hyprland raises its lockdead fallback ("oopsie daisy") with no client
#      left to unlock it.
#
# Safe to run at any time: it never unlocks a locked session, and it only
# touches eDP-1 when the kernel reports no external DisplayPort connected.

set -u

force=0
settle=3          # let Thunderbolt and kanshi finish reacting to the resume
if [ "${1:-}" = "--force" ]; then
  force=1
  settle=0        # a human is holding the key down; act now
fi

log() { logger -t display-lock-recover "$*"; }

hyprctl dispatch dpms on >/dev/null 2>&1
[ "$settle" -gt 0 ] && sleep "$settle"

# --- displays --------------------------------------------------------------
# Ask the kernel, not Hyprland: a phantom head outlives its connector.
external=0
for status in /sys/class/drm/card*-DP-*/status; do
  [ -r "$status" ] || continue
  [ "$(cat "$status")" = connected ] && external=1
done

if [ "$external" -eq 0 ]; then
  enabled=" $(hyprctl monitors -j 2>/dev/null | jq -r '[.[].name] | join(" ")') "

  # The panel comes back first: Hyprland silently ignores a request to disable
  # its only monitor, so a phantom can only be dropped once eDP-1 is up.
  case "$enabled" in
    *" eDP-1 "*) ;;
    *)
      log "no external display connected and eDP-1 is off; enabling the panel"
      hyprctl keyword monitor "eDP-1,2880x1920@120,0x0,2" >/dev/null 2>&1
      hyprctl dispatch dpms on >/dev/null 2>&1
      sleep 1
      enabled=" $(hyprctl monitors -j 2>/dev/null | jq -r '[.[].name] | join(" ")') "
      ;;
  esac

  # Dropping the phantom lets kanshi see the dock is gone and settle into
  # knuth_undocked on its own.
  for head in $enabled; do
    case "$head" in
      DP-*)
        log "dropping phantom head $head"
        hyprctl keyword monitor "$head,disable" >/dev/null 2>&1
        ;;
    esac
  done
fi

# --- lockscreen ------------------------------------------------------------
session="${XDG_SESSION_ID:-}"
if [ -z "$session" ]; then
  session=$(loginctl list-sessions --no-legend | awk -v u="$USER" '$3 == u && $4 != "-" {print $1; exit}')
fi
locked=$(loginctl show-session "$session" -p LockedHint --value 2>/dev/null)

if [ "$locked" = yes ]; then
  if [ "$force" -eq 1 ] && pidof -q hyprlock; then
    log "forced: replacing the running hyprlock"
    pkill -x hyprlock
    sleep 1
  fi
  if ! pidof -q hyprlock; then
    log "session is locked with no hyprlock (lockdead); relaunching under the watchdog"
    setsid "$HOME/scripts/hyprlock-watchdog.sh" --restore >/dev/null 2>&1 &
  fi
fi
