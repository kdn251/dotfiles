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
  _panel_close_others "$name"
}

# Opening one panel dismisses any other that is open, so clicking wifi then
# battery swaps panels instead of stacking two. Each panel holds its own lock,
# so they cannot see each other -- the pidfiles are the shared registry.
_panel_close_others() {
  local self="$1" f other pid closed=0
  for f in "$PANEL_RUNTIME"/waybar-panel-*.pid; do
    [ -e "$f" ] || continue
    other=$(basename "$f")
    other=${other#waybar-panel-}
    other=${other%.pid}
    [ "$other" = "$self" ] && continue
    pid=$(cat "$f" 2>/dev/null)
    [ -n "$pid" ] || continue
    if kill "$pid" 2>/dev/null; then
      closed=$((closed + 1))
    fi
    rm -f "$f"
  done
  # Killing the waiting notify-send does not remove the notification itself --
  # that lives in swaync. At this point ours is not posted yet, so the other
  # panel's notification is the most recent one.
  while [ "$closed" -gt 0 ]; do
    swaync-client --close-latest >/dev/null 2>&1
    closed=$((closed - 1))
  done

  # The ProtonVPN module is not a notification at all -- it shows/hides the
  # real app window like a dropdown, so the pidfile registry cannot see it.
  # Its own script exposes hide-if-visible, which is a no-op when hidden.
  if [ "$self" != "protonvpn" ] && [ -x "$HOME/scripts/protonvpn-waybar.sh" ]; then
    "$HOME/scripts/protonvpn-waybar.sh" hide-if-visible >/dev/null 2>&1 &
  fi
}

# Usable as a command, not just a sourced library, so the ProtonVPN dropdown
# (which is a real window, not a notification) can close the swaync panels
# when it opens:  panel-guard.sh close-others protonvpn
if [ "${BASH_SOURCE[0]}" = "$0" ] && [ "$1" = "close-others" ]; then
  _panel_close_others "${2:-__none__}"
  exit 0
fi

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
