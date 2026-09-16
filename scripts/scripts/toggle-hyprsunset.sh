#!/bin/bash
# Night light cycle: off -> level 1 -> level 2 -> off  (Super+Shift+N)
#
# Level changes go through `hyprctl hyprsunset temperature|gamma`, which
# applies live to the running instance. Killing and relaunching instead made
# the screen flash back to normal for a moment, because the compositor resets
# to identity in the gap before the new instance applies.
#
# The current level is read back over that same IPC rather than from a state
# file or the process arguments: a state file would drift if hyprsunset were
# killed some other way, and /proc/<pid>/cmdline still shows the ORIGINAL
# flags after an IPC change, so it would report the wrong level.
#
# Lower temperature = warmer/redder, lower gamma = dimmer.
L1_TEMP=3000; L1_GAMMA=75    # the original setting
L2_TEMP=2000; L2_GAMMA=50    # noticeably warmer and dimmer

# Apply a level. If hyprsunset is already up, adjust it in place over IPC --
# that is what removes the flash. Only a cold start spawns the daemon.
apply() {
  if pgrep -x hyprsunset >/dev/null 2>&1; then
    hyprctl hyprsunset gamma "$2" >/dev/null 2>&1
    hyprctl hyprsunset temperature "$1" >/dev/null 2>&1
    return
  fi
  # Detached on purpose: hyprsunset is a long-running daemon, so running it in
  # the foreground makes this script never return. Callers that wait on it
  # (the waybar display panel) would then hold their single-instance lock
  # forever and stop opening on subsequent clicks.
  setsid hyprsunset -t "$1" -g "$2" >/dev/null 2>&1 &
  disown
}

current_temp() {
  pgrep -x hyprsunset >/dev/null 2>&1 || return 1
  hyprctl hyprsunset temperature 2>/dev/null
}

case "$1" in
off)
  pkill -x hyprsunset
  exit 0
  ;;
1)
  apply "$L1_TEMP" "$L1_GAMMA"
  exit 0
  ;;
2)
  apply "$L2_TEMP" "$L2_GAMMA"
  exit 0
  ;;
level)
  # Report the active level: 0 off, 1, or 2. Used by the waybar display module.
  t=$(current_temp)
  if [ -z "$t" ]; then echo 0
  elif [ "$t" -le "$L2_TEMP" ]; then echo 2
  else echo 1
  fi
  exit 0
  ;;
esac

# No argument: advance the cycle.
t=$(current_temp)
if [ -z "$t" ]; then
  apply "$L1_TEMP" "$L1_GAMMA"
elif [ "$t" -gt "$L2_TEMP" ]; then
  apply "$L2_TEMP" "$L2_GAMMA"
else
  pkill -x hyprsunset
fi
