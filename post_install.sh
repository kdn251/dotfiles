#!/usr/bin/env bash
# Compatibility entry point. The main setup now includes these system steps.
set -euo pipefail
repo=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
exec bash "$repo/bootstrap/system.sh" "$repo"
