#!/bin/bash
# Toggle Picture-in-Picture for the YouTube webapp (Super+Shift+9).
#
# This drives Chromium's native video context menu rather than a shortcut,
# because neither alternative works here:
#   - Extension commands (wipeyy pip-switch, Dark Reader) do not fire in
#     Chromium app-mode windows at all. Verified both ways: the same synthetic
#     keys DO trigger them in a normal Brave window.
#   - Chromium ships no built-in PiP keybinding.
#
# ydotool, not wtype: requestPictureInPicture requires a genuine user gesture.
# wtype drives the virtual-keyboard protocol, which does not qualify -- the
# menu highlight moved correctly but Enter never activated the item. ydotool
# injects through uinput, which the browser treats as real hardware.

# Fast path: talk to the page directly over the DevTools protocol, which calls
# requestPictureInPicture/exitPictureInPicture outright -- no pointer movement,
# no menu, and nothing that breaks when Chromium reorders its context menu.
# Requires Brave started with --remote-debugging-port (see brave-flags.conf).
# Falls through to the menu-driving path below if that port is not up.
if [ -x "$HOME/scripts/yt-pip-cdp.py" ] && "$HOME/scripts/yt-pip-cdp.py" >/dev/null 2>&1; then
  exit 0
fi

WEBAPP_MATCH="brave-youtube"
PIP_TITLE="Picture in picture"

# Position of the video within the window, as a fraction of its size. YouTube
# puts the player top-left; this lands comfortably inside it.
VIDEO_FX=0.27
VIDEO_FY=0.32

# "Picture in picture" is the 5th ENABLED item in Chromium's video menu
# (disabled entries are skipped by keyboard navigation). Fragile if Chromium
# changes that menu -- if this stops working, open the menu manually and count.
DOWN_COUNT=5

KEY_SHIFT=42
KEY_DOWN=108
KEY_ENTER=28

pip_addr() {
  hyprctl clients -j 2>/dev/null |
    jq -r --arg t "$PIP_TITLE" '.[] | select(.title == $t) | .address' | head -1
}

# --- already in PiP: click the overlay's "back to tab" control ---
# Closing the window instead ends PiP abruptly and leaves the video PAUSED in
# the page. "Back to tab" hands playback back still running (verified via the
# PulseAudio sink staying uncorked across the transition).
#
# The control is the middle of three at the top right (minimize / back to tab /
# close), measured at 41px left of the right edge and 18px down. The overlay
# auto-hides when the pointer is idle and ignores clicks while hidden, so the
# pointer is jiggled first to bring it back.
ADDR=$(pip_addr)
if [ -n "$ADDR" ]; then
  read -r PX PY PW _ < <(
    hyprctl clients -j 2>/dev/null |
      jq -r --arg t "$PIP_TITLE" '.[] | select(.title == $t) |
        "\(.at[0]) \(.at[1]) \(.size[0]) \(.size[1])"' | head -1
  )
  OLD=$(hyprctl cursorpos 2>/dev/null | tr -d ' ')
  BX=$((PX + PW - 41))
  BY=$((PY + 18))
  hyprctl dispatch movecursor $((BX - 15)) $((BY + 9)) >/dev/null 2>&1
  sleep 0.25
  hyprctl dispatch movecursor "$BX" "$BY" >/dev/null 2>&1
  sleep 0.35
  ydotool click 0xC0 >/dev/null 2>&1
  sleep 1.2
  # Fall back to closing the window if the control moved; the video pauses in
  # that case, but PiP still exits rather than getting stuck.
  [ -n "$(pip_addr)" ] && hyprctl dispatch closewindow "address:$ADDR" >/dev/null 2>&1
  [ -n "$OLD" ] && hyprctl dispatch movecursor "${OLD%,*}" "${OLD#*,}" >/dev/null 2>&1
  exit 0
fi

# --- otherwise open it ---
read -r WADDR WX WY WW WH < <(
  hyprctl clients -j 2>/dev/null |
    jq -r --arg c "$WEBAPP_MATCH" '.[] | select(.class | test($c)) |
      "\(.address) \(.at[0]) \(.at[1]) \(.size[0]) \(.size[1])"' | head -1
)
if [ -z "$WADDR" ]; then
  notify-send -a "YT" -u low -t 3000 "Picture in Picture" "YouTube webapp is not open."
  exit 1
fi

# Put the pointer back where the user left it afterwards.
OLD=$(hyprctl cursorpos 2>/dev/null | tr -d ' ')
OLDX=${OLD%,*}
OLDY=${OLD#*,}

CX=$(awk -v x="$WX" -v w="$WW" -v f="$VIDEO_FX" 'BEGIN{printf "%d", x + w*f}')
CY=$(awk -v y="$WY" -v h="$WH" -v f="$VIDEO_FY" 'BEGIN{printf "%d", y + h*f}')

open_via_menu() {
  hyprctl dispatch focuswindow "address:$WADDR" >/dev/null 2>&1
  sleep 0.4
  hyprctl dispatch movecursor "$CX" "$CY" >/dev/null 2>&1
  sleep 0.3

  # Shift+right-click bypasses YouTube's own context menu and opens Chromium's.
  ydotool key ${KEY_SHIFT}:1 >/dev/null 2>&1
  ydotool click 0xC1 >/dev/null 2>&1
  ydotool key ${KEY_SHIFT}:0 >/dev/null 2>&1
  sleep 1.2

  for _ in $(seq "$DOWN_COUNT"); do
    ydotool key ${KEY_DOWN}:1 ${KEY_DOWN}:0 >/dev/null 2>&1
    sleep 0.12
  done
  sleep 0.25
  ydotool key ${KEY_ENTER}:1 ${KEY_ENTER}:0 >/dev/null 2>&1
  sleep 1.5
}

# One retry: pressing the key again straight after exiting PiP can land while
# the page is still settling, and the menu never opens.
open_via_menu
if [ -z "$(pip_addr)" ]; then
  wtype -k Escape 2>/dev/null
  sleep 1
  open_via_menu
fi
[ -n "$OLDX" ] && hyprctl dispatch movecursor "$OLDX" "$OLDY" >/dev/null 2>&1

if [ -z "$(pip_addr)" ]; then
  notify-send -a "YT" -u normal -t 3500 "Picture in Picture" \
    "Could not enter PiP. The context menu layout may have changed (DOWN_COUNT)."
fi
