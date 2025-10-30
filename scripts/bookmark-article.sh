#!/bin/bash

# New script for bookingmarking things to miniflux so bookmarks
# aree synced across devices

#!/bin/bash
BOOKMARKS_FILE="$HOME/.newsboat/bookmarked-urls.txt"
URLS_FILE="$HOME/.newsboat/urls"
MINIFLUX_URL="http://72.60.165.172:8080"
MINIFLUX_USER="knaught"
MINIFLUX_PASS="Binary"

URL="$1"
shift
TITLE="$*"

# Immediate feedback
notify-send "📚 Bookmarking..." "$TITLE" -t 3000

# Run the actual work in the background
(
  # Create file if doesn't exist
  touch "$BOOKMARKS_FILE"

  # Check if already bookmarked
  if grep -q "^$URL$" "$BOOKMARKS_FILE"; then
    notify-send "Already Bookmarked" "$TITLE" -t 2000
    exit 0
  fi

  # Add URL to bookmarks list
  echo "$URL" >>"$BOOKMARKS_FILE"

  # Star in Miniflux - try recent first, then expand if needed
  RESPONSE=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
    "${MINIFLUX_URL}/v1/entries?limit=500")

  ENTRY_ID=$(echo "$RESPONSE" | jq -r --arg url "$URL" \
    '.entries[] | select(.url == $url) | .id' | head -1)

  # If not found in recent, try larger set
  if [ -z "$ENTRY_ID" ] || [ "$ENTRY_ID" == "null" ]; then
    RESPONSE=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
      "${MINIFLUX_URL}/v1/entries?limit=5000")

    ENTRY_ID=$(echo "$RESPONSE" | jq -r --arg url "$URL" \
      '.entries[] | select(.url == $url) | .id' | head -1)
  fi

  if [ -n "$ENTRY_ID" ] && [ "$ENTRY_ID" != "null" ]; then
    curl -s -X PUT -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
      "${MINIFLUX_URL}/v1/entries/${ENTRY_ID}/bookmark"
    notify-send "📚 Bookmarked & Starred" "$TITLE" -t 2000
  else
    notify-send "📚 Bookmarked (entry not found)" "$TITLE" -t 2000
  fi

  # Update the bookmarks query
  # ~/scripts/update-bookmarks-query.sh
) &

# Exit immediately so Newsboat doesn't wait
exit 0

# Old script for bookingmarking things locally
# BOOKMARKS_FILE="$HOME/.newsboat/bookmarked-urls.txt"
# URLS_FILE="$HOME/.newsboat/urls"
# URL="$1"
# # TITLE="$2"
# TITLE="$*"
#
# # Create file if doesn't exist
# touch "$BOOKMARKS_FILE"
#
# # Check if already bookmarked
# if grep -q "^$URL$" "$BOOKMARKS_FILE"; then
#   notify-send "Already Bookmarked" "$TITLE" -t 2000
#   exit 0
# fi
#
# # Add URL to bookmarks list
# echo "$URL" >>"$BOOKMARKS_FILE"
# notify-send "📚 Bookmarked" "$TITLE" -t 2000
#
# # Update the bookmarks query
# ~/scripts/update-bookmarks-query.sh
