#!/usr/bin/env bash
# systemd coalesces wake/unlock events; wait briefly for networking to return.
set -u
stamp="${XDG_RUNTIME_DIR:-/tmp}/stream-live-resume-${UID}.stamp"
if [[ -f "$stamp" ]] && (( $(date +%s) - $(cat "$stamp") < 60 )); then
    exit 0
fi
for delay in 0 2 5 10 15 30; do
    (( delay == 0 )) || sleep "$delay"
    if curl --silent --fail --output /dev/null --max-time 5 https://www.twitch.tv/; then
        if "$HOME/scripts/update-live-list.sh"; then
            date +%s > "$stamp"
            exit 0
        fi
    fi
done
exit 1
