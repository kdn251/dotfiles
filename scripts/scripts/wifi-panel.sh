#!/bin/bash
# Wi-Fi panel for the waybar network module's on-click.
#
# Waybar tooltips are pango text and cannot hold a button, so the stats are
# rendered as a notification instead -- swaync supports action buttons, which
# gives the "click -> see stats -> button to open the TUI" flow.
#
# Note on the TUI: omarchy uses impala here, but impala drives iwd. This
# machine runs NetworkManager with the wpa_supplicant backend, so nmtui is
# the correct equivalent; installing impala would mean swapping the whole
# wireless backend.

TERM_CLASS="networkmanager-float"
TIMEOUT_MS=15000

# Single-instance guard: a second click closes the open panel rather
# than stacking another one. See panel-guard.sh.
source "$HOME/scripts/panel-guard.sh"
panel_guard wifi

dev=$(nmcli -t -f DEVICE,TYPE,STATE dev status |
  awk -F: '$2=="wifi" && $3=="connected"{print $1; exit}')

if [ -z "$dev" ]; then
  radio=$(nmcli radio wifi)
  body="Not connected.\nWi-Fi radio is <b>${radio}</b>."
  icon="network-wireless-offline"
else
  # Read cached AP details immediately. The default query can block on a scan
  # when results are over 30 seconds old; use the Rescan button for fresh scans.
  # Active AP row -> SSID / signal / bitrate / frequency
  IFS=$'\t' read -r ssid signal rate freq < <(
    nmcli -t -f ACTIVE,SSID,SIGNAL,RATE,FREQ dev wifi list ifname "$dev" --rescan no |
      awk -F: '$1=="yes"{printf "%s\t%s\t%s\t%s", $2, $3, $4, $5; exit}'
  )
  # GHz reads better than the raw "5180 MHz" nmcli reports
  ghz=$(awk -v f="${freq%% *}" 'BEGIN{ if (f > 0) printf "%.1f GHz", f/1000; else print "-" }')

  # Deliberately no IP or gateway here: this panel is on screen during screen
  # shares and recordings, and both leak the local subnet.
  body=$(printf '<tt>SSID     <b>%s</b>\nSignal   %s%%\nBand     %s\nRate     %s\nDevice   %s</tt>' \
    "$ssid" "$signal" "$ghz" "$rate" "$dev")
  icon="network-wireless-signal-excellent"
fi

action=$(panel_notify -a "Network" -i "$icon" -u low -t "$TIMEOUT_MS" \
  "Wi-Fi" "$body" \
  -A "tui=Open Network Manager" \
  -A "rescan=Rescan networks")

case "$action" in
tui) exec kitty --class "$TERM_CLASS" nmtui ;;
rescan)
  notify-send -a "Network" -u low -t 2000 "Wi-Fi" "Rescanning for networks..."
  if ! nmcli dev wifi rescan 2>/dev/null; then
    notify-send -a "Network" -u normal -t 3000 "Wi-Fi" "Could not rescan networks. Try again shortly."
  fi
  ;;
esac
