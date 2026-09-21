#!/bin/bash
# Called by Newsboat's ,d macro. Metadata, download progress, notifications,
# and the shared Waybar panel are handled by the same worker.
exec python3 "$(dirname "$(readlink -f "$0")")/newsboat-download.py" "$@"
