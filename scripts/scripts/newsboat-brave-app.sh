#!/bin/bash
# Open a URL in Brave's app mode (chromeless popup window).
# The window's class is auto-generated as brave-{host}__-Default by Brave.
# A windowrule in hyprland.conf catches all such app-mode windows except
# the music.youtube.com PWA, floating them as popups over newsboat.

url="$1"
# Save the original feed URL before rewriting Reddit links.
if command -v brave >/dev/null 2>&1; then
  python3 "$(dirname "$(readlink -f "$0")")/newsboat-history.py" record "$url" browser 2>/dev/null || true
fi

# Rewrite reddit links to old.reddit (less flashy, less addicting).
# Matches reddit.com, www.reddit.com, np.reddit.com, new.reddit.com — but not old.reddit.com.
url="$(printf '%s' "$url" | sed -E 's#^(https?://)(www\.|np\.|new\.)?reddit\.com#\1old.reddit.com#')"

# Browser diagnostics must not overwrite Newsboat's terminal display.
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/newsboat"
umask 077
mkdir -p "$state_dir" || exit 1
log="$state_dir/browser.log"
# Bound accumulated diagnostics while retaining the previous log for debugging.
if [ -f "$log" ] && [ "$(stat -c %s "$log")" -gt 1048576 ]; then
  mv -f "$log" "$log.1"
fi
exec brave --app="$url" >>"$log" 2>&1
