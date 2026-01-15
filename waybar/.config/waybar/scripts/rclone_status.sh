#!/bin/bash

# Fetch stats from rclone RC
STATS=$(rclone rc vfs/stats --rc-no-auth 2>/dev/null)

if [ $? -ne 0 ]; then
  # Rclone is not running or mount is down
  echo ""
  exit 0
fi

# Extract relevant numbers using jq
ACTIVE=$(echo "$STATS" | jq '.diskCache.uploadsInProgress')
QUEUED=$(echo "$STATS" | jq '.diskCache.uploadsQueued')
TOTAL=$((ACTIVE + QUEUED))

if [ "$TOTAL" -gt 0 ]; then
  # We are currently syncing
  SPEED=$(rclone rc core/stats --rc-no-auth | jq -r '.speed | . / 1024 / 1024 | round | tostring + " MB/s"')
  echo "{\"text\": \"󰕒 $TOTAL ($SPEED)\", \"tooltip\": \"Active: $ACTIVE\nQueued: $QUEUED\", \"class\": \"syncing\"}"
else
  # Everything is synced
  echo "{\"text\": \"󰄬\", \"tooltip\": \"All files synced to Google Drive\", \"class\": \"synced\"}"
fi
