#!/bin/bash
# Script to reliably toggle the 'pin' state for all floating Chatterino windows
# and the single floating MPV window.

# --- Configuration ---
LOG_FILE="/tmp/hypr_pip_toggle.log"
MPV_CLASS="mpv"
CHATTERINO_CLASS="com.chatterino.chatterino"
DISPATCH_DELAY="0.1" # Delay between window groups

# --- Logging setup (Clear log before running) ---
echo "--- $(date) ---" >"$LOG_FILE"
echo "Starting PiP Toggle Script (Pin ALL Floating Chatterino Fix)." >>"$LOG_FILE"

# Ensure jq is installed
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is not installed. Please install jq to use this script." >>"$LOG_FILE"
  exit 1
fi

# Function to toggle the 'pin' state for a single window via its unique address
toggle_pin_address() {
  local ADDRESS=$1
  local CLASS=$2

  # Dispatch the 'pin' command using the unique address.
  hyprctl dispatch pin address:"$ADDRESS"
  echo "DISPATCH: Toggled pin state for $CLASS via address $ADDRESS" >>"$LOG_FILE"
}

# --- Execution ---

# 1. Toggle ALL Floating Chatterino Windows

# Get a list of all floating Chatterino window addresses
CHATTERINO_ADDRESSES=$(hyprctl clients -j | jq -r ".[] | select(.class == \"$CHATTERINO_CLASS\" and .floating == true) | .address")

if [ -z "$CHATTERINO_ADDRESSES" ]; then
  echo "STATUS: No floating Chatterino windows found." >>"$LOG_FILE"
else
  echo "Toggling pin state for all floating Chatterino windows:" >>"$LOG_FILE"
  for ADDRESS in $CHATTERINO_ADDRESSES; do
    toggle_pin_address "$ADDRESS" "$CHATTERINO_CLASS"
  done
fi

# 2. Introduce a brief delay
sleep $DISPATCH_DELAY

# 3. Toggle MPV (assuming only one floating MPV window exists)

MPV_ADDRESS=$(hyprctl clients -j | jq -r ".[] | select(.class == \"$MPV_CLASS\" and .floating == true) | .address" | head -n 1)

if [ -z "$MPV_ADDRESS" ]; then
  echo "STATUS: No floating MPV window found." >>"$LOG_FILE"
else
  echo "Toggling pin state for MPV:" >>"$LOG_FILE"
  toggle_pin_address "$MPV_ADDRESS" "$MPV_CLASS"
fi

echo "Script finished." >>"$LOG_FILE"
