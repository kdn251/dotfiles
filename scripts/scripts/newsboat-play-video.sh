#!/bin/bash
# Return immediately while a detached worker starts and monitors playback.
exec python3 "$(dirname "$(readlink -f "$0")")/newsboat-play-video.py" "$@"
