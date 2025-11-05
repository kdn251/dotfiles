#!/bin/bash

# Wait a moment for monitor changes to apply
sleep 1

# Move only existing workspaces to the external monitor
hyprctl workspaces -j | jq -r '.[].id' | while read ws; do
  hyprctl dispatch moveworkspacetomonitor $ws DP-5 2>/dev/null
done

# Optional: Switch to workspace 1 on the external monitor
hyprctl dispatch workspace 1
