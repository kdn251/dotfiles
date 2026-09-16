#!/bin/bash
# Launch the YouTube webapp in an ISOLATED Brave profile.
#
# Why a separate profile: yt-pip-cdp.py toggles picture-in-picture over the
# DevTools protocol, which needs --remote-debugging-port. That port is
# unauthenticated -- any local process that connects gets full control of the
# browser it belongs to, including reading every cookie and acting as you on
# every logged-in site.
#
# Measured on the main profile before this split: 3020 cookies across 970
# sites, 13 live sessions, and 1046 HttpOnly cookies (a flag that stops
# JavaScript but NOT CDP). Putting the port on a profile whose only login is
# YouTube keeps the capability while shrinking the blast radius to that one
# account.
#
# The main profile therefore has NO debugging port -- brave-flags.conf is
# deliberately free of it, and the flag lives only here.

PROFILE="$HOME/.local/share/brave-youtube"
PORT="${YT_PIP_PORT:-9222}"
URL="${1:-https://youtube.com}"

mkdir -p "$PROFILE"

# Hyprland's group rule attaches an opening window to the FOCUSED window's
# group, so focus an existing webapp window first. Without this a new tab
# starts its own group on whatever workspace happened to be active -- which is
# how tabs ended up split across two workspaces during testing. Callers used to
# do this themselves; doing it here covers every path.
if [ "$1" != "--manage" ]; then
  _existing=$(hyprctl clients -j 2>/dev/null |
    jq -r '.[] | select(.class | test("brave.*youtube")) | .address' | head -1)
  if [ -n "$_existing" ]; then
    hyprctl dispatch focuswindow "address:$_existing" >/dev/null 2>&1
    sleep 0.3
  fi
fi

# `yt-webapp.sh --manage` opens this profile in a NORMAL window so its
# brave://extensions page is reachable -- app-mode windows have no UI for it.
# Anything installed here persists for later --app launches.
#
# Keep it to benign extensions. Extension pages are CDP targets too, so an
# extension holding credentials (a password manager, say) would hand its
# access to anything that connects to the debugging port, which is exactly
# the exposure this separate profile exists to avoid.
if [ "$1" = "--manage" ]; then
  exec brave \
    --user-data-dir="$PROFILE" \
    --ozone-platform=wayland \
    --new-window "brave://extensions"
fi

exec brave \
  --user-data-dir="$PROFILE" \
  --remote-debugging-port="$PORT" \
  --ozone-platform=wayland \
  --enable-features=TouchpadOverscrollHistoryNavigation \
  --app="$URL"
