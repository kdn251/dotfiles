#!/bin/bash
# Flip the focused window's parent split to horizontal, with the focused
# pane on the requested side (u=top, d=bottom).
#
# Strategy: swap tiles BEFORE togglesplit (when needed), so togglesplit is
# the final dispatch and nothing can undo it. Pre-swap uses movewindow l/r,
# which in a dwindle split swaps the two tile-tree siblings and ignores
# floating windows (e.g. MPV picture-in-picture).
#
# Assumes dwindle's togglesplit maps child[0] (left) → top, child[1] (right) → bottom.

dir="${1:?usage: $0 u|d}"

read -r focused_x ws addr < <(
  hyprctl activewindow -j |
    jq -r '"\(.at[0]) \(.workspace.id) \(.address)"'
)

sibling_x=$(
  hyprctl clients -j |
    jq -r --argjson ws "$ws" --arg addr "$addr" '
      [.[] | select(.workspace.id == $ws and .address != $addr and .floating == false)]
      | .[0].at[0] // empty'
)

if [[ -n "$sibling_x" ]]; then
  focused_is_left=$(( focused_x < sibling_x ? 1 : 0 ))

  if [[ "$dir" == "u" && "$focused_is_left" == "0" ]]; then
    hyprctl dispatch movewindow l
  elif [[ "$dir" == "d" && "$focused_is_left" == "1" ]]; then
    hyprctl dispatch movewindow r
  fi
fi

hyprctl dispatch layoutmsg togglesplit
