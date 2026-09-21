#!/bin/bash
# Refresh newsboat's cache. Run from cron every 15 minutes.

DB="$HOME/.newsboat/cache.db"

newsboat -x reload >/dev/null 2>&1

# Reclaim disk space. cleanup-on-quit prunes rows, but SQLite only marks those
# pages free inside the file and never returns them to the filesystem, so the
# cache sits at its high-water mark for good -- it had reached 135MB holding
# 27MB of live data. VACUUM needs exclusive access, so skip it while newsboat
# is open, and only bother once enough free pages have built up.
if ! pgrep -x newsboat >/dev/null 2>&1; then
  free=$(sqlite3 "$DB" 'PRAGMA freelist_count;' 2>/dev/null)
  if [ "${free:-0}" -gt 5000 ]; then
    sqlite3 "$DB" 'VACUUM;' >/dev/null 2>&1
  fi
fi
