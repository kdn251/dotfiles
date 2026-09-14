#!/bin/bash

# Check if hyprsunset is running
if pgrep -x "hyprsunset" >/dev/null; then
  # If it's running, kill it
  pkill -x "hyprsunset"
else
  # If it's not running, start it.
  # Detached on purpose: hyprsunset is a long-running daemon, so running it
  # in the foreground makes this script never return. Callers that wait on it
  # (the waybar display panel) would then hold their single-instance lock
  # forever and stop opening on subsequent clicks.
  setsid hyprsunset -t 3000 -g 75 >/dev/null 2>&1 &
  disown
fi
