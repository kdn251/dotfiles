#!/usr/bin/env bash
# Keep the distro binary available; the local build fixes Hyprland 0.57 clicks.
set -e
if [ -x "$HOME/.local/libexec/waybar-hypr57" ]; then
  exec "$HOME/.local/libexec/waybar-hypr57" "$@"
fi
exec /usr/bin/waybar "$@"
