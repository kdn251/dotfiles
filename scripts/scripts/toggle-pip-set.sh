#!/bin/bash
# Script to reliably toggle the 'pin' state for MPV, Vesktop, and Brave PiP.

# --- Configuration ---
LOG_FILE="/tmp/hypr_pip_toggle.log"
MPV_CLASS="mpv"
VESKTOP_CLASS="vesktop"
BRAVE_CLASS="brave-browser"

# --- Logging setup ---
echo "--- $(date) ---" >"$LOG_FILE"
echo "Starting PiP Toggle Script." >>"$LOG_FILE"

# Ensure jq is installed
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is not installed." >>"$LOG_FILE"
  exit 1
fi

# Function to toggle 'pin' via address
toggle_pin_address() {
  local ADDRESS=$1
  local LABEL=$2
  hyprctl dispatch pin address:"$ADDRESS"
  echo "DISPATCH: Toggled pin for $LABEL at $ADDRESS" >>"$LOG_FILE"
}

# 1. Handle MPV & Vesktop (Standard Classes)
# We also filter out any "special" workspaces (like -98) to avoid zombie windows
STANDARD_ADDRESSES=$(hyprctl clients -j | jq -r ".[] | select((.class == \"$MPV_CLASS\" or .class == \"$VESKTOP_CLASS\") and .floating == true and .workspace.id > 0) | .address")

for addr in $STANDARD_ADDRESSES; do
  toggle_pin_address "$addr" "Standard-App"
done

# 2. Handle Brave Picture-in-Picture
# Based on your logs, Brave PiP has an EMPTY class and specific title: "Picture in picture"
BRAVE_PIP_ADDRESSES=$(hyprctl clients -j | jq -r ".[] | select(.title == \"Picture in picture\" and .floating == true) | .address")

if [ -z "$BRAVE_PIP_ADDRESSES" ]; then
  echo "STATUS: No Brave PiP window found." >>"$LOG_FILE"
else
  for addr in $BRAVE_PIP_ADDRESSES; do
    toggle_pin_address "$addr" "Brave-PiP"
  done
fi

echo "Script finished." >>"$LOG_FILE"
