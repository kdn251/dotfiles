#!/bin/bash

# Script to bookmark an entry in Miniflux using a targeted API search.

# --- Configuration ---
BOOKMARKS_FILE="$HOME/.newsboat/bookmarked-urls.txt"
LOG_FILE="/tmp/miniflux_bookmark_final.log" # Cleaner final log
source "$HOME/.newsboat/miniflux_creds"
# ---------------------

URL="$1"
shift
TITLE="$*"

# Immediate feedback
notify-send "📚 Bookmarking..." "$TITLE" -t 3000

# Run the actual work in the background
(
  # --- Step 1: Handle Local Bookmarks (Same as before) ---
  touch "$BOOKMARKS_FILE"
  if grep -q "^$URL$" "$BOOKMARKS_FILE"; then
    notify-send "Already Bookmarked" "$TITLE" -t 2000
    exit 0
  fi
  echo "$URL" >>"$BOOKMARKS_FILE"

  # --------------------------------------------------------------------
  # --- Step 2: Targeted Search to get Miniflux entry ID (Efficient) ---
  # --------------------------------------------------------------------

  # Search Miniflux for the exact URL. The limit is low as we expect 0 or 1 result.
  RESPONSE=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
    "${MINIFLUX_URL}/v1/entries?search=\"$URL\"&limit=1")
  CURL_EXIT_CODE=$?

  if [ "$CURL_EXIT_CODE" -ne 0 ]; then
    echo "$(date): Curl failed with code $CURL_EXIT_CODE." >>"$LOG_FILE"
    notify-send "🚫 Bookmark FAILED" "Connection Error." -t 5000
    exit 1
  fi

  # Extract the entry ID using jq
  # Note: The Miniflux search parameter is reliable enough that checking URL match is optional.
  ENTRY_ID=$(echo "$RESPONSE" | jq -r '.entries[0].id' 2>/dev/null)

  # --------------------------------------------------------------------
  # --- Step 3: Check Result and Perform Bookmark Action ---
  # --------------------------------------------------------------------

  if [ -n "$ENTRY_ID" ] && [ "$ENTRY_ID" != "null" ]; then
    # Send the PUT request to bookmark/star the entry
    curl -s -X PUT -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
      "${MINIFLUX_URL}/v1/entries/${ENTRY_ID}/bookmark"

    echo "$(date): Successfully starred entry ID: $ENTRY_ID for URL: $URL" >>"$LOG_FILE"
    notify-send "📚 Bookmarked & Starred" "$TITLE" -t 2000
  else
    echo "$(date): FAILED to find entry ID for URL: $URL. Raw response: $RESPONSE" >>"$LOG_FILE"
    notify-send "📚 Bookmarked (entry not found)" "$TITLE" -t 2000
  fi

  # Update the bookmarks query (if you ever write this script)
  # ~/scripts/update-bookmarks-query.sh
) &

# Exit immediately so Newsboat doesn't wait
exit 0
