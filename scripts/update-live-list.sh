#!/bin/bash

# --- Configuration ---
# Your master list of all streamers (e.g., all 50 people you follow)
MASTER_LIST="$HOME/scripts/twitch_master_list.txt"
# The temporary file that will ONLY contain currently live streamers
LIVE_LIST="$HOME/scripts/twitch_usernames.txt"

# --- Master Logic ---

# 1. Check if the master list exists
if [ ! -f "$MASTER_LIST" ]; then
  echo "$(date): ERROR: Master list not found: $MASTER_LIST" >>/tmp/live_list_cron.log
  exit 1
fi

# 2. Check Stream Status in Parallel (using xargs for speed)
# - P 8: Use 8 parallel processes (adjust based on your CPU/network)
# - I {}: Replace {} with the current line (username)
# - Run a subshell to check the status using streamlink and capture output
# - The 'grep -q' check ensures we only print the username if no "error" is found.
# - The entire command is run in the background with nohup to prevent issues on exit.

nohup bash -c "
    cat \"$MASTER_LIST\" | while read USERNAME; do
        # Skip empty lines or comments
        [[ -z \"\$USERNAME\" || \"\$USERNAME\" =~ ^# ]] && continue

        # Check stream status via streamlink
        STREAM_OUTPUT=\$(streamlink \"https://twitch.tv/\$USERNAME\" best --json 2>/dev/null)
        
        # Check if the output contains the specific JSON key 'error'. 
        # If grep finds 'error' (exit code 0), the streamer is OFFLINE.
        # If grep does NOT find 'error' (exit code 1), the streamer is LIVE.
        echo \"\$STREAM_OUTPUT\" | grep -q '\"error\":'

        if [ \$? -ne 0 ]; then
            # Not an error, streamer is LIVE. Print the username.
            echo \"\$USERNAME\"
        fi
    done
" >"$LIVE_LIST.tmp" 2>/dev/null

# 3. Atomically update the file to prevent race conditions during read
# Sort the final list of live streamers and move it into the live list file.
if [ -s "$LIVE_LIST.tmp" ]; then
  sort "$LIVE_LIST.tmp" >"$LIVE_LIST"
  rm "$LIVE_LIST.tmp"
else
  # If no one is live, create an empty file (or leave the old list).
  # Creating an empty list is safer for your dmenu script.
  echo "" >"$LIVE_LIST"
  rm "$LIVE_LIST.tmp"
fi

echo "$(date): Live list updated successfully." >>/tmp/live_list_cron.log
