#!/bin/bash
# Wait for monitor changes to apply
sleep 1

# Move all workspaces back to laptop screen
hyprctl workspaces -j | jq -r '.[].id' | while read ws; do
  hyprctl dispatch moveworkspacetomonitor $ws eDP-1 2>/dev/null
done

# Switch to workspace 1
hyprctl dispatch workspace 1
