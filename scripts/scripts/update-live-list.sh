#!/bin/bash
# =================================================================
# SCRIPT: update_live_list.sh
# FUNCTION: Checks a master list of streamers for live status in
#           parallel and updates a clean list for the dmenu binding.
# SCHEDULE: Must be run by cron every X minutes.
# =================================================================

# --- Configuration ---
# Your master list of all 100 streamers
MASTER_LIST="$HOME/scripts/twitch_master_list.txt"
# The file that will ONLY contain currently LIVE, SORTED streamers
LIVE_LIST="$HOME/scripts/twitch_usernames.txt"
# Log file for cron job debugging
LOG_FILE="/tmp/live_list_cron.log"

# --- Main Logic ---

# 1. Check if the master list exists
if [ ! -f "$MASTER_LIST" ]; then
  echo "$(date): ERROR: Master list not found: $MASTER_LIST" >>"$LOG_FILE"
  exit 1
fi

# 2. Define the status checking function
# This function is executed in parallel by xargs below.
check_streamer_status() {
  local USERNAME="$1"
  [[ -z "$USERNAME" || "$USERNAME" =~ ^# ]] && return

  # Use --json and check if "streams" exists and isn't null
  STREAM_OUTPUT=$(streamlink "https://twitch.tv/$USERNAME" --json 2>/dev/null)

  # Check if metadata exists (this confirms they are live)
  IS_LIVE=$(echo "$STREAM_OUTPUT" | jq -r '.metadata.title // empty')

  if [ -n "$IS_LIVE" ]; then
    # Extract the game/category safely using jq
    GAME=$(echo "$STREAM_OUTPUT" | jq -r '.metadata.category // "Unknown"')
    echo "$USERNAME ($GAME)"
  fi
}

# Export the function so xargs can use it in parallel subshells
export -f check_streamer_status

# 3. Parallel Execution using xargs
# - xargs reads the master list line by line.
# - -I {} passes each line (username) as the argument {} to the function.
# - -P 8 runs 8 processes simultaneously (adjust '8' based on your CPU cores).
# - Output is written to a temporary file.
cat "$MASTER_LIST" | xargs -I {} -P 8 bash -c 'check_streamer_status "$@"' _ {} >"$LIVE_LIST.tmp" 2>/dev/null

# 4. Atomically update the file: SORT the temporary list and move it.
if [ -s "$LIVE_LIST.tmp" ]; then
  # Sort the final list of live streamers alphabetically and write to the final file
  sort "$LIVE_LIST.tmp" >"$LIVE_LIST"
  rm "$LIVE_LIST.tmp"
else
  # If no one is live, create an empty file.
  echo "" >"$LIVE_LIST"
  rm "$LIVE_LIST.tmp" 2>/dev/null
fi

echo "$(date): Live list updated successfully and sorted." >>"$LOG_FILE"
