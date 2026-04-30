#!/bin/bash
# Open a URL in Brave's app mode (chromeless popup window).
# The window's class is auto-generated as brave-{host}__-Default by Brave.
# A windowrule in hyprland.conf catches all such app-mode windows except
# the music.youtube.com PWA, floating them as popups over newsboat.
exec brave --app="$1"
