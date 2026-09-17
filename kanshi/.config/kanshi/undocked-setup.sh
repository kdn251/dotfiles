#!/bin/bash
# Preserve the pre-hotplug workspace and recreate Waybar on the settled output.
exec "$HOME/scripts/workspace-hotplug.py" --apply undocked
