#!/bin/bash
# Keep the existing startup entry and single-instance lock.
exec flock -n /tmp/restore-pip-position.lock python3 "$(dirname "$(readlink -f "$0")")/restore-pip-position.py"
