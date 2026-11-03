#!/bin/bash

# =========================================================
# Configuration
# =========================================================
RECORDING_DIR="$HOME/Videos/Recordings"
STATE_FILE="/tmp/waybar_record_state"
RECORDING_STATUS_FILE="/tmp/recording.txt"
OUTPUT_FILE="$RECORDING_DIR/recording_$(date +%Y%m%d_%H%M%S)"

# Prefer the desk camera; when undocked, explicitly use laptop video and audio.
configure_capture_devices() {
  local devices microphone
  devices=$(v4l2-ctl --list-devices)
  WEBCAM_DEVICE=$(printf '%s\n' "$devices" | grep -A 1 "MX Brio" | grep -o '/dev/video[0-9]\+' | head -n 1)
  WEBCAM_AUDIO_SOURCE='default'

  if [ -z "$WEBCAM_DEVICE" ]; then
    WEBCAM_DEVICE=$(printf '%s\n' "$devices" | grep -A 1 "Laptop Webcam" | grep -o '/dev/video[0-9]\+' | head -n 1)
    if [ -z "$WEBCAM_DEVICE" ]; then
      notify-send -u critical "Recording Error" "Neither MX Brio nor laptop webcam was found."
      return 1
    fi

    # Select the internal microphone even if a headset is the system default.
    microphone=$(pactl -f json list sources | python3 -c '
import json, sys
for source in json.load(sys.stdin):
    for port in source.get("ports", []):
        if port["name"] == "analog-input-internal-mic":
            print(source["name"], port["name"])
            sys.exit(0)
sys.exit(1)
')
    if [ -z "$microphone" ]; then
      notify-send -u critical "Recording Error" "The built-in microphone was not found."
      return 1
    fi
    local microphone_port
    read -r WEBCAM_AUDIO_SOURCE microphone_port <<<"$microphone"
    if ! pactl set-source-port "$WEBCAM_AUDIO_SOURCE" "$microphone_port"; then
      notify-send -u critical "Recording Error" "Could not select the built-in microphone."
      return 1
    fi
  fi
}

WEBCAM_RESOLUTION="1920x1080"

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

  # Remove recording status from tmp file so waybar updates
  echo "" >"$RECORDING_STATUS_FILE"

  # Read the PIDs
  read -r SCREEN_PID WEBCAM_PID <"$STATE_FILE"

  sleep 3
  # 1. Stop Webcam Recording (FFmpeg)
  # Use SIGINT for grace, but MKV handles abrupt stops well if needed.
  # kill -INT "$WEBCAM_PID" 2>/dev/null
  kill -9 "$WEBCAM_PID"
  sleep 1

  # 2. Stop Screen Recording (wf-recorder)
  kill -TERM "$SCREEN_PID" 2>/dev/null
  sleep 1

  # Remove the state file
  rm -f "$STATE_FILE"

  notify-send "Recording Stopped" "Files saved to $RECORDING_DIR"

else
  # --- STARTING RECORDING (MKV specific flags) ---
  configure_capture_devices || exit 1
  echo "Starting new recording with $WEBCAM_DEVICE and $WEBCAM_AUDIO_SOURCE..."

  # Add recording status from tmp file so waybar updates
  echo "recording *" >"$RECORDING_STATUS_FILE"

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
