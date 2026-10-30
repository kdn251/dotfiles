#!/usr/bin/env bash
set -e
# Import this session before any Wayland service is started.
dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP HYPRLAND_INSTANCE_SIGNATURE XDG_SESSION_ID
systemctl --user start hyprland-session.target
systemctl --user restart kanshi.service hypridle.service
systemctl --user start waybar.service
systemctl --user start moonlight-cursor.service

# Keep the stream picker warm so its hotkey only needs to show the window.
python3 "$HOME/scripts/stream-picker.py" --daemon >/dev/null 2>&1 &

# Reuse resolver imports and HTTPS connections across stream selections.
python3 "$HOME/scripts/twitch_resolver.py" --daemon >/dev/null 2>&1 &
