#!/bin/bash

FOCUSED=$(hyprctl activewindow -j)
TITLE=$(echo $FOCUSED | jq -r '.title')
FULLSCREEN=$(echo $FOCUSED | jq -r '.fullscreen')

if [[ "$TITLE" == "Picture in picture" || "$TITLE" == "Picture-in-Picture" ]]; then
  if [[ "$FULLSCREEN" == "0" ]]; then
    hyprctl dispatch pin disable
    hyprctl dispatch fullscreen 0
  else
    hyprctl dispatch fullscreen 0
    hyprctl dispatch pin enable
  fi
fi
