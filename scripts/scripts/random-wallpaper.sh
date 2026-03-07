#!/bin/bash

# Configuration
WALLPAPER_DIR="$HOME/pictures/wallpapers"
HYPRLOCK_CONF="$HOME/.config/hypr/hyprlock.conf"
PATH=$PATH:/usr/bin:/bin

# 1. Get current wallpaper path and ensure it's an absolute path
CURRENT_WALLPAPER=$(hyprctl hyprpaper listactive | cut -d ' ' -f 3 | head -n 1)

# 2. Prepare the list
# We want to make sure the current wallpaper is exactly at the top of the input stream
ALL_FILES=$(find -L "$WALLPAPER_DIR" -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.jpeg" \) | sort)
# Put the current one first, then everything else (excluding the current one)
LIST_TO_FZF=$(
  echo "$CURRENT_WALLPAPER"
  echo "$ALL_FILES" | grep -vF "$CURRENT_WALLPAPER"
)

# 3. Launch fzf
SELECTED=$(echo "$LIST_TO_FZF" | fzf --ansi \
  --preview '
        img={}
        # Update the wallpaper background live
        hyprctl hyprpaper preload "$img" > /dev/null
        hyprctl hyprpaper wallpaper ",$img" > /dev/null
        # Show the preview in kitty
        kitty +kitten icat --clear --stdin no --silent --transfer-mode memory --place 30x15@65x5 "$img"
    ' \
  --preview-window=right:60%:noborder \
  --layout=reverse --margin=1 --padding=1 \
  --prompt="󰸉 Select Wallpaper > " \
  --border="rounded" \
  --no-sort) # Crucial: prevents fzf from re-sorting our list

# 4. Finalize
if [ -n "$SELECTED" ]; then
  if [ -f "$HYPRLOCK_CONF" ]; then
    WALL_REL="${SELECTED/#$HOME/\~}"
    sed -i "s|^\s*path\s*=.*|    path = $WALL_REL|" "$HYPRLOCK_CONF"
  fi
  notify-send "Wallpaper Set" "$(basename "$SELECTED")"
fi
