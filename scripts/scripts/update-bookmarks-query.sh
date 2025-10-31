#!/bin/bash

# New script for maintaining booksmarks across devices with miniflux

BOOKMARKS_FILE="$HOME/.newsboat/bookmarked-urls.txt"
URLS_FILE="$HOME/.newsboat/urls"

# Fetch all starred/bookmarked entries from Miniflux
STARRED_URLS=$(curl -s -u "$MINIFLUX_USER:$MINIFLUX_PASS" \
  "${MINIFLUX_URL}/v1/entries?starred=true&limit=10000" |
  jq -r '.entries[].url')

# Rebuild the bookmarks file from Miniflux's starred list
echo "$STARRED_URLS" >"$BOOKMARKS_FILE"

# Remove old bookmarks query
sed -i '/^"query:Bookmarks:/d' "$URLS_FILE"

# Build query from bookmarked URLs
if [ -f "$BOOKMARKS_FILE" ] && [ -s "$BOOKMARKS_FILE" ]; then
  # Extract just unique identifiers from URLs
  URLS_PATTERN=$(cat "$BOOKMARKS_FILE" | sed 's/https\?:\/\///' | sed 's/[^a-zA-Z0-9_-]/.*/g' | tr '\n' '|' | sed 's/|$//')

  if [ -n "$URLS_PATTERN" ]; then
    # Insert at top of file with proper escaping
    sed -i "2i\"query:Bookmarks:link =~ \\\\\"($URLS_PATTERN)\\\\\"\" bookmarks" "$URLS_FILE"
  fi
fi

# Old script for maintaining bookmarks locally
# BOOKMARKS_FILE="$HOME/.newsboat/bookmarked-urls.txt"
# URLS_FILE="$HOME/.newsboat/urls"
#
# # Remove old bookmarks query
# sed -i '/^"query:Bookmarks:/d' "$URLS_FILE"
#
# # Build query from bookmarked URLs
# if [ -f "$BOOKMARKS_FILE" ] && [ -s "$BOOKMARKS_FILE" ]; then
#   # Extract just unique identifiers from URLs (like video IDs or article slugs)
#   # For now, use a simpler approach - match any part of the URL
#   URLS_PATTERN=$(cat "$BOOKMARKS_FILE" | sed 's/https\?:\/\///' | sed 's/[^a-zA-Z0-9_-]/.*/g' | tr '\n' '|' | sed 's/|$//')
#
#   if [ -n "$URLS_PATTERN" ]; then
#     # Insert at top of file with proper escaping (use \\\\ for sed)
#     sed -i "2i\"query:Bookmarks:link =~ \\\\\"($URLS_PATTERN)\\\\\"\" bookmarks" "$URLS_FILE"
#   fi
# fi
