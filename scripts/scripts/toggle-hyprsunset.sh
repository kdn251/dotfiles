#!/bin/bash

# Check if hyprsunset is running
if pgrep -x "hyprsunset" >/dev/null; then
  # If it's running, kill it
  pkill -x "hyprsunset"
else
  # If it's not running, start it
  hyprsunset -t 3000 -g 75
fi
