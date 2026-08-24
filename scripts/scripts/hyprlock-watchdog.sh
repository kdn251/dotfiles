#!/usr/bin/env bash
# hypridle lock_cmd: run hyprlock and keep it alive until the session is unlocked.
#
# Why: on a docked resume Hyprland re-enumerates outputs and drops hyprlock's
# Wayland connection; hyprlock 0.9.6 treats that POLLHUP as fatal
# (RASSERT at src/core/hyprlock.cpp:414) and aborts, leaving Hyprland's red
# "oopsie daisy" fallback with no way to unlock except a TTY re-login.
# Hyprland's misc:allow_session_lock_restore=true (hyprland.conf) lets a fresh
# hyprlock re-acquire the lock, so we simply relaunch it while it keeps dying.
#
# Exit code contract (hyprlock 0.9.6 src/main.cpp): 0 = unlocked normally,
# 1 = refused to start (config error, lock denied), >=128 = killed by a signal
# (SIGABRT from the RASSERT). Relaunches use --grace 0 so a crash can never
# open a mouse-wiggle unlock window; the initial launch keeps hyprlock.conf's grace.

LOG="${XDG_CACHE_HOME:-$HOME/.cache}/hyprlock-watchdog.log"
MAX_RELAUNCH=60      # ~1 min of back-to-back failures before giving up
mkdir -p "$(dirname "$LOG")"

# Another hyprlock already holds the lock (e.g. lock_cmd fired twice): nothing to do.
if pidof -q hyprlock; then
  exit 0
fi

# Rotate the log so it only ever holds the current lock session.
: > "$LOG"
echo "$(date '+%F %T') watchdog: launching hyprlock" >> "$LOG"

attempt=0
args=(--grace 5)   # hyprlock.conf's old general:grace, now CLI-only
while true; do
  hyprlock "${args[@]}" >> "$LOG" 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "$(date '+%F %T') watchdog: hyprlock exited cleanly (unlocked)" >> "$LOG"
    exit 0
  fi

  attempt=$((attempt + 1))
  echo "$(date '+%F %T') watchdog: hyprlock died rc=$rc (attempt $attempt/$MAX_RELAUNCH), relaunching" >> "$LOG"
  logger -t hyprlock-watchdog "hyprlock died rc=$rc (attempt $attempt/$MAX_RELAUNCH), relaunching"

  if [ "$attempt" -ge "$MAX_RELAUNCH" ]; then
    logger -t hyprlock-watchdog "giving up after $attempt failures; unlock from a TTY: hyprctl keyword misc:allow_session_lock_restore 1; hyprlock"
    exit 1
  fi

  # Give Hyprland a moment to finish whatever output change killed us.
  sleep 1
  args=(--grace 0 --immediate-render --no-fade-in)
done
