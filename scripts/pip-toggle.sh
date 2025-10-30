#!/bin/bash

# Get coordinates of picture in picture 
# extension with `hyprctl cursorpos`
# Coordinates to click
X_COORD=780
Y_COORD=58

# Function to ensure ydotoold is running
ensure_ydotoold() {
    if ! pgrep -x "ydotoold" > /dev/null; then
        # Start ydotoold in background and redirect output to /dev/null
        ydotoold --socket-path="/run/user/1000/.ydotool_socket" --socket-own="$(id -u):$(id -g)" > /dev/null 2>&1 &
        # Wait a moment for the daemon to start
        sleep 1
    fi
}

# Check if ydotool is installed
if command -v ydotool &> /dev/null; then
    ensure_ydotoold
    # Using ydotool for Wayland - redirect output to /dev/null to keep script quiet

    ydotool mousemove --absolute $X_COORD $Y_COORD > /dev/null 2>&1
    ydotool click --repeat 1 0xC0
    exit 0
else
    notify-send "Error" "ydotool not found. Please install it."
    exit 1
fi
