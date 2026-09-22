#!/usr/bin/env bash
# Build the optional page-scrolling Newsboat used by newsboat-session.py.
set -euo pipefail
repo=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
build_dir="${XDG_CACHE_HOME:-$HOME/.cache}/newsboat-paged"
install_dir="$HOME/.local/lib/newsboat-paged"
mkdir -p "$build_dir" "$install_dir"
curl -fL https://github.com/newsboat/newsboat/archive/refs/tags/r2.44.tar.gz -o "$build_dir/source.tar.gz"
printf '%s  %s\n' aa3d144f737a39567100e82effd1dfd9a0dbcc705332ec66d0c35a750a9a3b10 "$build_dir/source.tar.gz" | sha256sum -c -
tar -xzf "$build_dir/source.tar.gz" -C "$build_dir"
cd "$build_dir/newsboat-r2.44"
patch -p1 < "$repo/newsboat/patches/paged-lists.patch"
patch -p1 < "$repo/newsboat/patches/download-status.patch"
patch -p1 < "$repo/newsboat/patches/live-queries.patch"
patch -p1 < "$repo/newsboat/patches/starred-badges.patch"
patch -p1 < "$repo/newsboat/patches/highlight-selection.patch"
patch -p1 < "$repo/newsboat/patches/all-sources.patch"
patch -p1 < "$repo/newsboat/patches/stable-badge-position.patch"
patch -p1 < "$repo/newsboat/patches/smooth-starred-entry.patch"
patch -p1 < "$repo/newsboat/patches/all-unread-count.patch"
patch -p1 < "$repo/newsboat/patches/all-unread-filter.patch"
patch -p1 < "$repo/newsboat/patches/instant-view-return.patch"
patch -p1 < "$repo/newsboat/patches/starred-total-count.patch"
patch -p1 < "$repo/newsboat/patches/downloads-total-count.patch"
patch -p1 < "$repo/newsboat/patches/live-list-removal.patch"
patch -p1 < "$repo/newsboat/patches/undo-actions.patch"
patch -p1 < "$repo/newsboat/patches/saved-list-row-numbers.patch"
make -j"${NEWSBOAT_BUILD_JOBS:-4}" WARNFLAGS="-Werror -Wall -Wextra -Wunreachable-code -Wno-error=unused-function" newsboat
install -m 755 newsboat "$install_dir/newsboat.new"
mv "$install_dir/newsboat.new" "$install_dir/newsboat"
