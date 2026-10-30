#!/bin/bash
# Shift+C supplies the invoking player's socket and PID, on every platform.
exec python3 "$(dirname "$(readlink -f "$0")")/mpv_clip.py" "$@"
