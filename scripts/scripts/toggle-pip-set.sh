#!/bin/bash
# Refactored for speed and to prevent IPC deadlocks

LOG_FILE="/tmp/hypr_pip_toggle.log"
exec >>"$LOG_FILE" 2>&1

echo "--- $(date) ---"

# 1. Get all client data in ONE call and parse addresses in one go
# We combine the logic for MPV, Vesktop, and Brave PiP into a single jq filter
TARGET_ADDRESSES=$(hyprctl clients -j | jq -r '
  .[] | 
  select(
    (.floating == true) and 
    (
      (.class == "mpv" or .class == "vesktop") or 
      (.title == "Picture in picture" and .class == "brave-browser")
    )
  ) | .address')

if [ -z "$TARGET_ADDRESSES" ]; then
  echo "STATUS: No matching PiP windows found."
  exit 0
fi

# 2. Batch the dispatch commands
# Instead of calling hyprctl in a loop (which causes the lag),
# we build a single string and send it once.
BATCH_CMD=""
for addr in $TARGET_ADDRESSES; do
  BATCH_CMD+="dispatch pin address:$addr; "
done

# 3. Execute everything in a single socket write
hyprctl --batch "$BATCH_CMD"

echo "DISPATCH: Sent batch pin toggle for: $TARGET_ADDRESSES"
echo "Script finished."
