#!/bin/bash

# Configuration
WALLPAPER_DIR="$HOME/pictures/wallpapers"
HYPRPAPER_CONF="$HOME/.config/hypr/hyprpaper.conf"
HYPRLOCK_CONF="$HOME/.config/hypr/hyprlock.conf"
PATH=$PATH:/usr/bin:/bin

# 1. Current wallpaper from hyprpaper.conf (first path line), expand leading ~
CURRENT_WALLPAPER=$(grep -E '^\s*path\s*=' "$HYPRPAPER_CONF" | head -n1 | sed -E 's/^\s*path\s*=\s*//')
CURRENT_WALLPAPER="${CURRENT_WALLPAPER/#\~/$HOME}"

# 2. Build list with current wallpaper at top
ALL_FILES=$(find -L "$WALLPAPER_DIR" -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.jpeg" \) | sort)
LIST_TO_FZF=$(
  echo "$CURRENT_WALLPAPER"
  echo "$ALL_FILES" | grep -vF "$CURRENT_WALLPAPER"
)

# 3. fzf with thumbnail preview
SELECTED=$(echo "$LIST_TO_FZF" | fzf --ansi \
  --delimiter=/ --with-nth=-1 \
  --preview 'kitty +kitten icat --clear --stdin no --silent --transfer-mode memory --place 30x15@65x5 {}' \
  --preview-window=right:60%:noborder \
  --layout=reverse --margin=1 --padding=1 \
  --prompt="󰸉 Select Wallpaper > " \
  --border="rounded" \
  --no-sort)

# 4. Apply: rewrite hyprpaper.conf paths and restart the daemon
if [ -n "$SELECTED" ]; then
  WALL_REL="${SELECTED/#$HOME/\~}"
  sed -i -E "s|^(\s*path\s*=\s*).*|\1$WALL_REL|" "$HYPRPAPER_CONF"
  pkill -x hyprpaper
  sleep 0.2
  hyprctl dispatch exec hyprpaper >/dev/null
  if [ -f "$HYPRLOCK_CONF" ]; then
    sed -i -E "s|^(\s*path\s*=\s*).*|\1$WALL_REL|" "$HYPRLOCK_CONF"
  fi

  if command -v wallust >/dev/null; then
    if wallust run -q "$SELECTED"; then
      pkill -SIGUSR2 waybar
      pkill -SIGUSR1 -x kitty
      command -v makoctl >/dev/null && makoctl reload
      hyprctl reload >/dev/null
    fi
  fi

  notify-send "Wallpaper Set" "$(basename "$SELECTED")"
fi
