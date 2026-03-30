#!/usr/bin/env zsh
pkill -f "title=ThunarPreview"
mpv --image-display-duration=inf \
    --player-operation-mode=pseudo-gui \
    --title="ThunarPreview" "$1" &!
