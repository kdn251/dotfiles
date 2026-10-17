#!/bin/bash
# Build against the installed compositor headers; the plugin also checks its ABI.
set -euo pipefail
src="$HOME/scripts/hypr-plugins/pip-workspace-focus.cpp"
cache="${XDG_CACHE_HOME:-$HOME/.cache}/hyprland/plugins"
mkdir -p "$cache"
exec 9>"$cache/pip-workspace-focus.lock"
flock 9
if hyprctl plugin list -j | python3 -c 'import json,sys; sys.exit(not any(p.get("name") == "pip-workspace-focus" for p in json.load(sys.stdin)))'; then
    exit 0
fi
output="$cache/pip-workspace-focus.so"
# Rebuild on every login so compositor upgrades never reuse an old binary.
g++ -shared -fPIC -std=c++23 -O2 $(pkg-config --cflags hyprland) "$src" -o "$output.tmp"
mv "$output.tmp" "$output"
hyprctl plugin load "$output"
