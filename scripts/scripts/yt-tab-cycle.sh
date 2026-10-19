#!/bin/bash
# Ctrl+Tab / Ctrl+Shift+Tab: cycle tabs in a Hyprland window group.
#
# Hyprland binds are global, so binding CTRL,Tab directly swallowed the key in
# EVERY window -- Brave's own tab switching stopped working. This forwards the
# key to the application whenever the focused window is not a tab group.
#
# Usage: yt-tab-cycle.sh f|b

set -u
DIR="${1:-f}"
GUARD="${XDG_RUNTIME_DIR:-/tmp}/yt-tab-cycle.passthrough"

# Re-entry guard. The passthrough below synthesises the very key that triggered
# this script; if Hyprland routes that back through the keybind system we would
# recurse forever. The flag exists only for the microseconds the dispatch takes,
# so it never delays genuine repeated presses.
if [ -e "$GUARD" ]; then
  # Stale flag from a killed run would wedge the key permanently, so ignore one
  # older than a second.
  if [ -z "$(find "$GUARD" -mmin +0.016 2>/dev/null)" ]; then
    exit 0
  fi
  rm -f "$GUARD"
fi

read -r ADDR MEMBERS CLASS < <(hyprctl activewindow -j 2>/dev/null | python3 -c '
import json, sys
try:
    w = json.load(sys.stdin)
except Exception:
    print("none 0"); raise SystemExit
print(w.get("address") or "none", len(w.get("grouped") or []), w.get("class") or "unknown")
')

# A group of one is still a group (windowrule group set always makes one per
# window), and cycling it does nothing -- treat it as "not tabbed".
if [ "${MEMBERS:-0}" -gt 1 ]; then
  exec hyprctl dispatch changegroupactive "$DIR" >/dev/null
fi

[ "$ADDR" = none ] && exit 0

# Not tabbed: give the key to the application. sendshortcut names the modifiers
# explicitly, so the combo the app receives does not depend on which keys are
# still physically held down.
MOD=CTRL
KEY=Tab
[ "$DIR" = b ] && MOD="CTRL SHIFT"
# Brave exposes sequential tab selection separately from Ctrl+Tab cycling.
# Avoid forwarding Shift+Tab while the physical modifiers are held: use the
# dedicated previous/next-tab shortcuts for ordinary Brave windows instead.
case "$CLASS" in
  brave|brave-browser|Brave-browser)
    MOD=CTRL
    KEY=Page_Down
    [ "$DIR" = b ] && KEY=Page_Up
    ;;
esac
touch "$GUARD"
trap 'rm -f "$GUARD"' EXIT
hyprctl dispatch sendshortcut "$MOD,$KEY,address:$ADDR" >/dev/null
