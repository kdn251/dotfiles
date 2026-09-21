#!/bin/bash
# Return success to the Newsboat macro only once mpv actually starts playback.
exec python3 "$(dirname "$(readlink -f "$0")")/newsboat-play-video.py" "$@"
