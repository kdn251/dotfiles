#!/bin/bash
# Script to toggle visibility of ALL floating Chatterino windows using the 'opaque' property
# and relying on the existing windowrulev2 = opacity -0.1 -0.1,... rule for visual effect.

# --- Configuration ---
LOG_FILE="/tmp/hypr_chat_toggle.log"
CHATTERINO_CLASS="com.chatterino.chatterino"
DISPATCH_DELAY="0.05"

# --- Logging setup (Clear log before running) ---
echo "--- $(date) ---" >"$LOG_FILE"
echo "Starting Chat Visibility Toggle Script (SIMPLE OPAQUE TOGGLE)." >>"$LOG_FILE"

# --- Execution ---

# 1. Get a list of all floating Chatterino window addresses
# We rely on the generic floating class match, as the 'opaque' property toggle is fast and should not conflict.
CHATTERINO_ADDRESSES=$(hyprctl clients -j | jq -r ".[] | select(.class == \"$CHATTERINO_CLASS\" and .floating == true) | .address")

if [ -z "$CHATTERINO_ADDRESSES" ]; then
  echo "STATUS: No floating Chatterino windows found. Aborting toggle." >>"$LOG_FILE"
  exit 1
fi

echo "Toggling opaque property for all floating Chatterino windows:" >>"$LOG_FILE"

# 2. Apply the 'opaque toggle' action to ALL collected addresses
for ADDRESS in $CHATTERINO_ADDRESSES; do
  # The 'opaque toggle' dispatcher is the simplest way to flip visibility state.
  hyprctl dispatch setprop address:"$ADDRESS" opaque toggle
  echo "DISPATCHED: setprop address:$ADDRESS opaque toggle" >>"$LOG_FILE"
  sleep $DISPATCH_DELAY
done

echo "Script finished." >>"$LOG_FILE"
