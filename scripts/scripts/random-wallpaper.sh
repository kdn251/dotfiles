#!/bin/bash

# Use absolute paths for stability
WALLPAPER_DIR="$HOME/pictures/wallpapers"
HYPRLOCK_CONF="$HOME/.config/hypr/hyprlock.conf"

# Ensure we can find hyprctl and kitty
PATH=$PATH:/usr/bin:/bin

export -f hyprctl
update_bg() {
  # Check if hyprpaper is actually running
  if pgrep -x "hyprpaper" >/dev/null; then
    hyprctl hyprpaper preload "$1" >/dev/null
    hyprctl hyprpaper wallpaper ",$1" >/dev/null
  fi
}
export -f update_bg

# The Picker
# Note: --transfer-mode=memory is often more reliable for fzf previews
SELECTED=$(find -L "$WALLPAPER_DIR" -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.jpeg" \) |
  fzf --preview 'bash -c "update_bg {} && kitty +kitten icat --clear --stdin no --silent --transfer-mode memory --place 30x15@65x5 {}"' \
    --preview-window=right:60%:noborder \
    --layout=reverse --margin=1 --padding=1 \
    --prompt="󰸉 Wallpaper > " \
    --border="rounded")

# Finalize
if [ -n "$SELECTED" ]; then
  update_bg "$SELECTED"
  if [ -f "$HYPRLOCK_CONF" ]; then
    # Use sed with a different delimiter in case of spaces in paths
    WALL_REL="${SELECTED/#$HOME/\~}"
    sed -i "s|^\s*path\s*=.*|    path = $WALL_REL|" "$HYPRLOCK_CONF"
  fi
fi
