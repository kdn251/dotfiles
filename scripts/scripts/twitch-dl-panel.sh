#!/bin/bash
# The existing Twitch VOD module also tracks manual YouTube/Twitch downloads.
# Polling bypasses the panel lock; clicking retains the shared toggle behavior.
helper="$(dirname "$(readlink -f "$0")")/newsboat-download.py"
if [ "${1:-}" = "--waybar" ]; then
  exec python3 "$helper" --waybar
fi
source "$HOME/scripts/panel-guard.sh"
panel_guard twitchdl
python3 "$helper" --panel
