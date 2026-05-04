#!/bin/bash
# Open a URL in Brave's app mode (chromeless popup window).
# The window's class is auto-generated as brave-{host}__-Default by Brave.
# A windowrule in hyprland.conf catches all such app-mode windows except
# the music.youtube.com PWA, floating them as popups over newsboat.

url="$1"

# Rewrite reddit links to old.reddit (less flashy, less addicting).
# Matches reddit.com, www.reddit.com, np.reddit.com, new.reddit.com — but not old.reddit.com.
url="$(printf '%s' "$url" | sed -E 's#^(https?://)(www\.|np\.|new\.)?reddit\.com#\1old.reddit.com#')"

exec brave --app="$url"
