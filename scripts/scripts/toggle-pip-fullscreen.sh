#!/bin/bash
# Shared native fullscreen transaction for Mod+F and MPV F.
exec python3 "$(dirname "$(readlink -f "$0")")/toggle-pip-fullscreen.py" "$@"
