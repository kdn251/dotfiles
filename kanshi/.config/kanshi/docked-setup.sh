#!/bin/bash

# Wait a moment for monitor changes to apply
sleep 1

# Pick the first enabled non-internal monitor (the external display kanshi just brought up).
EXTERNAL=$(hyprctl monitors -j | jq -r '[.[] | select(.name | startswith("eDP") | not)] | .[0].name // empty')

if [ -z "$EXTERNAL" ]; then
  echo "docked-setup.sh: no external monitor found, skipping workspace move" >&2
  exit 0
fi

# Move regular (positive-id) workspaces to the external monitor.
# Skip special workspaces (negative ids) — they can't be moved with this dispatcher
# and the leading '-' confuses hyprctl's flag parser.
hyprctl workspaces -j | jq -r '.[] | select(.id > 0) | .id' | while read ws; do
  hyprctl dispatch moveworkspacetomonitor "$ws $EXTERNAL" 2>/dev/null
done

# Switch to workspace 1 so the user lands on a populated workspace, not the empty one
# that Hyprland auto-creates for the new monitor.
hyprctl dispatch workspace 1

# Brave: relaunch at 1.33x device scale to compensate for the external monitor.
~/.config/kanshi/brave-rezoom.sh 1.33
