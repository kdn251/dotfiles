#!/bin/bash
# Refresh newsboat's cache. Run from cron every 15 minutes.

DB="$HOME/.newsboat/cache.db"

# The normal desktop uses this patched binary; distro Newsboat cannot parse
# the custom undo-checkpoint bindings in our configuration.
newsboat_bin="$HOME/.local/lib/newsboat-paged/newsboat"
[ -x "$newsboat_bin" ] || newsboat_bin=$(command -v newsboat)
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/newsboat"
mkdir -p "$state_dir"
exec 9>"$state_dir/refresh.lock"
flock -n 9 || exit 0
if "$newsboat_bin" -x reload >"$state_dir/refresh.log" 2>&1; then
  date -Is >"$state_dir/last-refresh-success"
else
  status=$?
  printf 'Newsboat refresh failed; see %s/refresh.log\n' "$state_dir" >&2
  exit "$status"
fi

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
