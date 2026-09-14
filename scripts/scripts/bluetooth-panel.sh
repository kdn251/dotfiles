#!/bin/bash
# Bluetooth panel for the waybar bluetooth module's on-click.
#
# Same shape as wifi-panel.sh / battery-panel.sh: a swaync notification with
# action buttons. Each paired device gets a button; connected ones are marked
# and toggle to disconnect. A final button opens bluetui for anything this
# panel does not cover (pairing, removing, scanning).
#
# NOTE: power state is managed with `bluetoothctl power`, never `rfkill block`.
# rfkill leaves the waybar module unable to turn the adapter back on.

# App name is "BT", not "Bluetooth": swaync maps the latter to a themed icon
# that fails to render, leaving a broken-image placeholder in the panel.
TIMEOUT_MS=15000

# Single-instance guard: a second click closes the open panel rather
# than stacking another one. See panel-guard.sh.
source "$HOME/scripts/panel-guard.sh"
panel_guard bluetooth
MAX_LABEL=18

powered=$(bluetoothctl show 2>/dev/null | awk '/Powered:/{print $2; exit}')

if [ "$powered" != "yes" ]; then
  action=$(panel_notify -a "BT" -u low -t "$TIMEOUT_MS" \
    "Bluetooth" "<tt>Adapter  <b>off</b></tt>" \
    -A "poweron=Turn On" -A "manage=Manage...")
  case "$action" in
  poweron)
    bluetoothctl power on >/dev/null
    notify-send -a "BT" -u low -t 2000 "Bluetooth" "Adapter powered on."
    ;;
  manage) exec kitty --class bluetui-float bluetui ;;
  esac
  exit 0
fi

# Paired devices -> parallel arrays of mac / name
macs=() names=()
while read -r _ mac name; do
  [ -n "$mac" ] || continue
  macs+=("$mac")
  names+=("$name")
done < <(bluetoothctl devices Paired 2>/dev/null)

connected=$(bluetoothctl devices Connected 2>/dev/null | awk '{print $2}')

is_connected() { printf '%s\n' "$connected" | grep -qx "$1"; }

# Body: what is connected right now, with battery where the device reports it
active_lines=()
if [ -n "$connected" ]; then
  while read -r mac; do
    [ -n "$mac" ] || continue
    nm=""
    for i in "${!macs[@]}"; do
      [ "${macs[$i]}" = "$mac" ] && nm="${names[$i]}"
    done
    batt=$(bluetoothctl info "$mac" 2>/dev/null |
      sed -n 's/.*Battery Percentage:.*(\([0-9]\+\)).*/\1/p' | head -1)
    if [ -n "$batt" ]; then
      active_lines+=("$(printf '%s (%s%%)' "${nm:-$mac}" "$batt")")
    else
      active_lines+=("${nm:-$mac}")
    fi
  done < <(printf '%s\n' "$connected")
fi

if [ "${#active_lines[@]}" -eq 0 ]; then
  active="nothing connected"
else
  # First device sits on the "Active" line; any others align under it.
  active="${active_lines[0]}"
  for extra in "${active_lines[@]:1}"; do
    active+=$(printf '\n%-9s%s' "" "$extra")
  done
fi

body=$(printf '<tt>Adapter  <b>on</b>\nActive   %s</tt>' "$active")

# One action per paired device, keyed by index so device names with odd
# characters cannot break the action name
args=()
for i in "${!macs[@]}"; do
  label="${names[$i]}"
  [ "${#label}" -gt "$MAX_LABEL" ] && label="${label:0:$((MAX_LABEL - 1))}…"
  is_connected "${macs[$i]}" && label="$label ✓"
  args+=(-A "dev$i=$label")
done
args+=(-A "manage=Manage...")

action=$(panel_notify -a "BT" -u low -t "$TIMEOUT_MS" \
  "Bluetooth" "$body" "${args[@]}")

case "$action" in
manage) exec kitty --class bluetui-float bluetui ;;
dev*)
  idx="${action#dev}"
  mac="${macs[$idx]}"
  name="${names[$idx]}"
  if is_connected "$mac"; then
    bluetoothctl disconnect "$mac" >/dev/null &&
      notify-send -a "BT" -u low -t 2500 "Bluetooth" "Disconnected $name"
  else
    notify-send -a "BT" -u low -t 2000 "Bluetooth" "Connecting to $name..."
    if bluetoothctl connect "$mac" >/dev/null 2>&1; then
      notify-send -a "BT" -u low -t 2500 "Bluetooth" "Connected $name"
    else
      notify-send -a "BT" -u normal -t 3500 "Bluetooth" "Could not connect to $name"
    fi
  fi
  ;;
esac
