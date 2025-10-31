#!/bin/bash

# New script for unbookmarking items across devices with miniflux

BOOKMARKS_FILE="$HOME/.newsboat/bookmarked-urls.txt"

URL="$1"
shift
TITLE="$*"

# Immediate feedback
notify-send "🗑️ Unbookmarking..." "$TITLE" -t 3000

# Run in background
(
  if [ -f "$BOOKMARKS_FILE" ]; then
    # Remove URL from bookmarks
    sed -i "\|^$URL$|d" "$BOOKMARKS_FILE"

    # Unstar in Miniflux
    RESPONSE=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
      "${MINIFLUX_URL}/v1/entries?limit=500")

    ENTRY_ID=$(echo "$RESPONSE" | jq -r --arg url "$URL" \
      '.entries[] | select(.url == $url) | .id' | head -1)

    # Try larger set if not found
    if [ -z "$ENTRY_ID" ] || [ "$ENTRY_ID" == "null" ]; then
      RESPONSE=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
        "${MINIFLUX_URL}/v1/entries?limit=5000")

      ENTRY_ID=$(echo "$RESPONSE" | jq -r --arg url "$URL" \
        '.entries[] | select(.url == $url) | .id' | head -1)
    fi

    if [ -n "$ENTRY_ID" ] && [ "$ENTRY_ID" != "null" ]; then
      curl -s -X PUT -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
        "${MINIFLUX_URL}/v1/entries/${ENTRY_ID}/bookmark"
    fi

    notify-send "🗑️ Unbookmarked" "$TITLE" -t 2000

    # Update the bookmarks query
    # ~/scripts/update-bookmarks-query.sh
  else
    notify-send "Not Bookmarked" "$TITLE" -t 2000
  fi
) &

exit 0

# Old script for unbookmarking items locally
# BOOKMARKS_FILE="$HOME/.newsboat/bookmarked-urls.txt"
# URL="$1"
# # TITLE="$2"
# TITLE="$*"
#
# if [ -f "$BOOKMARKS_FILE" ]; then
#   # Remove URL from bookmarks
#   sed -i "\|^$URL$|d" "$BOOKMARKS_FILE"
#   notify-send "🗑️ Unbookmarked" "$TITLE" -t 2000
#
#   # Update the bookmarks query
#   ~/scripts/update-bookmarks-query.sh
# else
#   notify-send "Not Bookmarked" "$TITLE" -t 2000
# fi
