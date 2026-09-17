#!/usr/bin/env bash
# Subscribe so changes from the notification panel also update immediately.
set -o pipefail
swaync-client --subscribe-waybar | jq --unbuffered -c '
  (.alt | startswith("dnd-")) as $dnd |
  {
    text: (if $dnd then "󰂛" else "󰂚" end),
    class: (if $dnd then "dnd" else "normal" end),
    tooltip: ((if $dnd then "Do Not Disturb: on" else "Do Not Disturb: off" end)
      + "\nLeft-click: toggle DND\nRight-click: notification history")
  }
'
