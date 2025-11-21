#!/bin/bash

# =========================================================
# Configuration
# =========================================================
RECORDING_DIR="$HOME/Videos/Recordings"
STATE_FILE="/tmp/waybar_record_state"
OUTPUT_FILE="$RECORDING_DIR/recording_$(date +%Y%m%d_%H%M%S)"

# Device specific settings
WEBCAM_DEVICE="/dev/video2"
WEBCAM_RESOLUTION="1920x1080"
# Using 'default' is the safest choice for PulseAudio/PipeWire unless another source is required.
WEBCAM_AUDIO_SOURCE='default'

# Waybar Signal: Adjust +8 if necessary
WAYBAR_SIGNAL="pkill -RTMIN+8 waybar"

# Ensure the recording directory exists
mkdir -p "$RECORDING_DIR"

# =========================================================
# Check State and Toggle Recording
# =========================================================

# Check if recording is already active (state file exists)
if [ -f "$STATE_FILE" ]; then
  # --- STOPPING RECORDING (PID-based kill) ---
  echo "Stopping current recording..."

  # Read the PIDs
  read -r SCREEN_PID WEBCAM_PID <"$STATE_FILE"

  sleep 3
  # 1. Stop Webcam Recording (FFmpeg)
  # Use SIGINT for grace, but MKV handles abrupt stops well if needed.
  kill -INT "$WEBCAM_PID" 2>/dev/null
  sleep 1

  # 2. Stop Screen Recording (wf-recorder)
  kill -TERM "$SCREEN_PID" 2>/dev/null
  sleep 1

  # Remove the state file
  rm -f "$STATE_FILE"

  notify-send "Recording Stopped" "Files saved to $RECORDING_DIR"

else
  # --- STARTING RECORDING (MKV specific flags) ---
  echo "Starting new recording..."

  # 🛑 AGGRESSIVE PRE-CHECK: Kill any process using the webcam
  LOCKING_PIDS=$(fuser "$WEBCAM_DEVICE" 2>/dev/null)
  if [ -n "$LOCKING_PIDS" ]; then
    echo "Webcam ($WEBCAM_DEVICE) was busy. Killing processes: $LOCKING_PIDS"
    kill -9 $LOCKING_PIDS 2>/dev/null
    sleep 1
  fi

  # Use 'setsid' for guaranteed process detachment.

  # 1. Start Screen Recording (wf-recorder) in the background
  setsid wf-recorder -g --overwrite -f "$OUTPUT_FILE.screen.mp4" >/dev/null 2>&1 &
  SCREEN_PID=$!

  # 2. Start Webcam Recording (ffmpeg) - NOW USES MKV
  setsid ffmpeg -nostdin \
    -f v4l2 -i "$WEBCAM_DEVICE" \
    -f pulse -i "$WEBCAM_AUDIO_SOURCE" \
    -s "$WEBCAM_RESOLUTION" \
    -c:v libx264 -preset ultrafast \
    -c:a aac \
    "$OUTPUT_FILE.webcam.mkv" >/dev/null 2>&1 &
  WEBCAM_PID=$!

  sleep 1 # Wait briefly for processes to start

  # Write BOTH PIDs to the state file
  echo "$SCREEN_PID $WEBCAM_PID" >"$STATE_FILE"

  notify-send "Recording Started" "Screen: $OUTPUT_FILE.screen.mp4\nWebcam: $OUTPUT_FILE.webcam.mkv"
fi

# =========================================================
# Waybar Update
# =========================================================

# Trigger Waybar to refresh the custom module instantly
$WAYBAR_SIGNAL
