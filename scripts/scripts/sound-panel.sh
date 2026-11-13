#!/bin/bash
# Use the common popup guard, with a native slider instead of notification actions.
source "$HOME/scripts/panel-guard.sh"
panel_guard sound
printf '%s' "$$" > "$PANEL_PIDFILE"
exec python3 "$(dirname "$(readlink -f "$0")")/sound-panel.py"
