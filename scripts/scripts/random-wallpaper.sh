#!/bin/bash

# Config paths
WALLPAPER_DIR="$HOME/pictures/wallpapers"
CACHE_DIR="$HOME/.cache/wallpaper-thumbs"
HYPRLOCK_CONF="$HOME/.config/hypr/hyprlock.conf"

# Create cache dir if it doesn't exist
mkdir -p "$CACHE_DIR"

# 1. Generate/Update Thumbnails
# This keeps the menu fast. It only creates thumbs for new files.
find "$WALLPAPER_DIR" -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.jpeg" \) | while read -r img; do
  thumb="$CACHE_DIR/$(basename "$img")"
  if [ ! -f "$thumb" ] || [ "$img" -nt "$thumb" ]; then
    magick "$img" -thumbnail 200x200^ -gravity center -extent 200x200 "$thumb"
  fi
done

# 2. Build the list for wofi
# Syntax: img:<path>:text:<label>
WOFI_LIST=""
while read -r img; do
  thumb="$CACHE_DIR/$(basename "$img")"
  WOFI_LIST+="img:$thumb:text:$(basename "$img")\n"
done < <(find "$WALLPAPER_DIR" -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.jpeg" \))

# 3. Show the menu
# --allow-images is the magic flag here
SELECTED=$(echo -e "$WOFI_LIST" | wofi --dmenu --allow-images -i -p "Select Wallpaper" --width 400 --height 500)

[ -z "$SELECTED" ] && exit 0

# Extract the filename from the selection
FILE_NAME=$(echo "$SELECTED" | sed 's/.*text://')
FULL_PATH="$WALLPAPER_DIR/$FILE_NAME"

# 4. Apply the wallpaper
if [ -f "$FULL_PATH" ]; then
  hyprctl hyprpaper preload "$FULL_PATH"
  hyprctl hyprpaper wallpaper ",$FULL_PATH"

  # Update hyprlock
  if [ -f "$HYPRLOCK_CONF" ]; then
    WALL_REL="${FULL_PATH/#$HOME/\~}"
    sed -i "s|^\s*path\s*=.*|    path = $WALL_REL|" "$HYPRLOCK_CONF"
  fi

  notify-send "Wallpaper Set" "$FILE_NAME"
fi
