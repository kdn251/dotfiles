#!/bin/bash

# Define a unique title for the camera window
WINDOW_TITLE="Webcam_Floating_Window"

# ----------------------------------------------------------------------
# New Logic: Find the PID of the specific camera instance
# We use pgrep -f to match the full command line used to launch the app.
# ----------------------------------------------------------------------
PID=$(pgrep -f "mpv --no-audio --title=$WINDOW_TITLE")

# Check if a PID was found (i.e., if the camera is currently running)
if [ -n "$PID" ]; then
  # If running (PID is not empty), kill the specific process by its PID
  echo "Webcam running (PID: $PID). Killing process..."
  kill "$PID"
else
  # If not running, launch the camera feed with mpv
  echo "Webcam not running. Launching mpv..."

  # mpv launch command details:
  # --no-audio: Prevent audio input/output setup, focusing purely on video
  # --title: Crucial for Hyprland rules and the kill/check logic above
  # --input-vo-keyboard=no: Disables keyboard input for the mpv window (prevents accidental closing/pausing)
  # --autofit=30%: Set initial size to 30% of the screen width/height (Hyprland size rule might override this)
  # /dev/video0: The standard video input device

  mpv \
    --no-audio \
    --title="$WINDOW_TITLE" \
    --input-vo-keyboard=no \
    --autofit=30% \
    /dev/video0 &
fi
