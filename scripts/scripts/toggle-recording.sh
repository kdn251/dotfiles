#!/bin/bash

# Path to your main recording script
RECORD_SCRIPT="$HOME/scripts/record.sh"

# Check if the record script exists and is executable
if [ -x "$RECORD_SCRIPT" ]; then
  # Simply execute it; the logic inside record.sh handles the toggle
  bash "$RECORD_SCRIPT"
else
  notify-send "Recording Error" "Could not find record.sh at $RECORD_SCRIPT"
  exit 1
fi
