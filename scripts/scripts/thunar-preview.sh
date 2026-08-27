#!/usr/bin/env bash
# Quick Look-style preview for Thunar. Bound to Space via uca.xml + accels.scm.
# Space toggles: closes if previewing the same file, switches if a different one.
# Arrow keys inside the preview step through the folder's other previewable files.
set -u

STATE=/tmp/thunar-preview-file
PLAYLIST=/tmp/thunar-preview-playlist.m3u
FILE="${1:-}"

pid=$(pgrep -f 'wayland-app-id=thunar-preview' | head -1)
if [[ -n $pid ]]; then
    last=$(cat "$STATE" 2>/dev/null || true)
    kill "$pid"
    [[ -z $FILE || $FILE == "$last" ]] && exit 0
fi

[[ -z $FILE ]] && exit 0
printf '%s' "$FILE" > "$STATE"

# Siblings mpv can preview, in Thunar-like natural sort order
find "$(dirname "$FILE")" -maxdepth 1 -type f \( \
    -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' \
    -o -iname '*.webp' -o -iname '*.bmp' -o -iname '*.tif' -o -iname '*.tiff' \
    -o -iname '*.avif' -o -iname '*.jxl' \
    -o -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.webm' -o -iname '*.mov' -o -iname '*.avi' \
    -o -iname '*.mp3' -o -iname '*.flac' -o -iname '*.opus' -o -iname '*.ogg' \
    -o -iname '*.m4a' -o -iname '*.wav' \) 2>/dev/null > "$PLAYLIST.raw"

# Match Thunar's current sort so next/prev follow the on-screen order
col=$(xfconf-query -c thunar -p /last-sort-column 2>/dev/null || echo THUNAR_COLUMN_NAME)
ord=$(xfconf-query -c thunar -p /last-sort-order 2>/dev/null || echo GTK_SORT_ASCENDING)
rev=; [[ $ord == GTK_SORT_DESCENDING ]] && rev=-r
case $col in
    THUNAR_COLUMN_DATE_MODIFIED)
        while IFS= read -r f; do printf '%s\t%s\n' "$(stat -c %Y "$f")" "$f"; done < "$PLAYLIST.raw" \
            | sort -n $rev -k1,1 | cut -f2- ;;
    THUNAR_COLUMN_SIZE)
        while IFS= read -r f; do printf '%s\t%s\n' "$(stat -c %s "$f")" "$f"; done < "$PLAYLIST.raw" \
            | sort -n $rev -k1,1 | cut -f2- ;;
    *)  sort -V $rev "$PLAYLIST.raw" ;;
esac > "$PLAYLIST"
rm -f "$PLAYLIST.raw"

idx=$(grep -nxF -m1 "$FILE" "$PLAYLIST" | cut -d: -f1)
if [[ -z $idx ]]; then
    printf '%s\n' "$FILE" > "$PLAYLIST"
    idx=1
fi

exec mpv --no-config \
    --vo=gpu --gpu-api=opengl \
    --wayland-app-id=thunar-preview \
    --title='Preview: ${filename}' \
    --no-terminal --force-window=yes \
    --autofit-larger=70%x75% --autofit-smaller=30%x30% \
    --image-display-duration=inf \
    --loop-file=inf \
    --input-conf="$HOME/.config/mpv/thunar-preview-input.conf" \
    --playlist="$PLAYLIST" --playlist-start=$((idx - 1))
