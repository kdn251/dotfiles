#!/bin/bash
# Script to reliably toggle the 'pin' state for all floating MPV windows.
# --- Configuration ---
LOG_FILE="/tmp/hypr_pip_toggle.log"
MPV_CLASS="mpv"
VESKTOP_CLASS="vesktop"
# --- Logging setup (Clear log before running) ---
echo "--- $(date) ---" >"$LOG_FILE"
echo "Starting PiP Toggle Script (Pin MPV and Vesktop windows)." >>"$LOG_FILE"
# Ensure jq is installed
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is not installed. Please install jq to use this script." >>"$LOG_FILE"
  exit 1
fi
# Function to toggle the 'pin' state for a single window via its unique address
toggle_pin_address() {
  local ADDRESS=$1
  local CLASS=$2
  hyprctl dispatch pin address:"$ADDRESS"
  echo "DISPATCH: Toggled pin state for $CLASS via address $ADDRESS" >>"$LOG_FILE"
}
# Toggle all floating MPV windows
MPV_ADDRESSES=$(hyprctl clients -j | jq -r ".[] | select(.class == \"$MPV_CLASS\" and .floating == true) | .address")

if [ -z "$MPV_ADDRESSES" ]; then
  echo "STATUS: No floating MPV window found." >>"$LOG_FILE"
else
  echo "Toggling pin state for MPV:" >>"$LOG_FILE"
  while IFS= read -r addr; do
    toggle_pin_address "$addr" "$MPV_CLASS"
  done <<<"$MPV_ADDRESSES"
fi

# Toggle Vesktop
VESKTOP_ADDRESS=$(hyprctl clients -j | jq -r ".[] | select(.class == \"$VESKTOP_CLASS\" and .floating == true) | .address" | head -n 1)

if [ -z "$VESKTOP_ADDRESS" ]; then
  echo "STATUS: No floating Vesktop window found." >>"$LOG_FILE"
else
  echo "Toggling pin state for Vesktop:" >>"$LOG_FILE"
  toggle_pin_address "$VESKTOP_ADDRESS" "$VESKTOP_CLASS"
fi
echo "Script finished." >>"$LOG_FILE"
