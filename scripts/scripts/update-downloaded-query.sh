#!/bin/bash
exec python3 "$(dirname "$(readlink -f "$0")")/newsboat_media.py" rebuild
