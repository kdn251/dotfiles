#!/bin/bash
# Restart Brave with --force-device-scale-factor=$1 (or without if no arg).
# No-op if Brave isn't already running, or if it's already at the desired scale.

SCALE="$1"

MAIN_PID=""
MAIN_CMD=""
for pid in $(pgrep -x brave 2>/dev/null); do
  cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
  if ! echo "$cmd" | grep -q -- '--type='; then
    MAIN_PID=$pid
    MAIN_CMD=$cmd
    break
  fi
done

if [ -z "$MAIN_PID" ]; then
  exit 0
fi

if [ -n "$SCALE" ]; then
  echo "$MAIN_CMD" | grep -q -- "--force-device-scale-factor=$SCALE" && exit 0
else
  echo "$MAIN_CMD" | grep -q -- '--force-device-scale-factor' || exit 0
fi

kill -TERM "$MAIN_PID" 2>/dev/null

for _ in $(seq 1 50); do
  kill -0 "$MAIN_PID" 2>/dev/null || break
  sleep 0.1
done

if pgrep -x brave >/dev/null; then
  pkill -KILL -x brave 2>/dev/null
  sleep 0.3
fi

if [ -n "$SCALE" ]; then
  setsid -f brave --force-device-scale-factor="$SCALE" >/dev/null 2>&1
else
  setsid -f brave >/dev/null 2>&1
fi

# Move any brave-browser windows that appear within ~12s onto workspace 2
# silently (without yanking the user's focus). Session-restore can spawn
# multiple windows, so we keep watching and dedupe by address.
(
  seen=""
  for _ in $(seq 1 60); do
    while IFS= read -r addr; do
      [ -z "$addr" ] && continue
      case " $seen " in *" $addr "*) continue ;; esac
      hyprctl dispatch movetoworkspacesilent "2,address:$addr" >/dev/null 2>&1
      seen="$seen $addr"
    done < <(hyprctl clients -j 2>/dev/null | jq -r '.[] | select(.class == "brave-browser") | .address')
    sleep 0.2
  done
) &
disown
