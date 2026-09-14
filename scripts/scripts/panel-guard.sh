#!/bin/bash
# Shared single-instance guard for the waybar click panels
# (wifi-panel.sh, battery-panel.sh, bluetooth-panel.sh).
#
# Each panel blocks on `notify-send --wait` for up to 15s while it waits for a
# button press. Without a guard every click spawns another instance and swaync
# stacks the notifications, so clicking an icon a few times left several panels
# on screen. With this, a second click dismisses the open panel instead:
# click to open, click again to close.
#
# The clicks pile up in the first place because swaync's entry animation is
# ~400ms (transition-time), which is long enough to read as "nothing happened".

PANEL_RUNTIME="${XDG_RUNTIME_DIR:-/tmp}"

panel_guard() {
  local name="$1"
  PANEL_PIDFILE="$PANEL_RUNTIME/waybar-panel-$name.pid"
  exec 9>"$PANEL_RUNTIME/waybar-panel-$name.lock"
  if ! flock -n 9; then
    # Another instance holds the lock, so a panel is already up: close it.
    #
    # Two steps are needed. Killing the waiting notify-send only ends the
    # client that is blocked on a button press -- the notification itself
    # lives in swaync and would sit there until its timeout. So dismiss it
    # through swaync as well.
    [ -r "$PANEL_PIDFILE" ] && kill "$(cat "$PANEL_PIDFILE")" 2>/dev/null
    swaync-client --close-latest >/dev/null 2>&1
    exit 0
  fi
  trap 'rm -f "$PANEL_PIDFILE"' EXIT
}

# notify-send backgrounded so its PID is recorded (letting a second click kill
# it), then waited on; echoes the chosen action exactly like notify-send does.
panel_notify() {
  local out np
  out=$(mktemp)
  notify-send "$@" >"$out" 2>/dev/null &
  np=$!
  printf '%s' "$np" >"$PANEL_PIDFILE"
  wait "$np" 2>/dev/null
  cat "$out"
  rm -f "$out"
}
