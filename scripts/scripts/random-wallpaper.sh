#!/bin/bash

source "$HOME/.zshrc" 2>/dev/null

WALLPAPER_DIR="$HOME/pictures/wallpapers"
HYPRLOCK_CONF="$HOME/.config/hypr/hyprlock.conf"

# Check if wallpaper directory exists and has files
if [ ! -d "$WALLPAPER_DIR" ] || [ -z "$(ls -A "$WALLPAPER_DIR")" ]; then
  notify-send "Wallpaper Error" "No wallpapers found in $WALLPAPER_DIR"
  exit 1
fi

# Select random wallpaper
# Use -L to dereference symbolic links and search the actual file locations
WALLPAPER=$(find -L "$WALLPAPER_DIR" -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.jpeg" \) | shuf -n 1)

# Update hyprpaper via hyprctl
hyprctl hyprpaper preload "$WALLPAPER"
hyprctl hyprpaper wallpaper ",$WALLPAPER"

# Update hyprlock config
if [ -f "$HYPRLOCK_CONF" ]; then
  # Replace the path line, keeping the tilde format for consistency
  WALLPAPER_RELATIVE="${WALLPAPER/#$HOME/\~}"
  sed -i "s|^\s*path\s*=.*|    path = $WALLPAPER_RELATIVE|" "$HYPRLOCK_CONF"
fi
