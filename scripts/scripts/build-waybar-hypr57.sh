#!/usr/bin/env bash
# Build Waybar 0.15's original workspace UI with Hyprland 0.57 click commands.
# Requires Waybar build dependencies plus meson, ninja, and glib2-devel.
# Arch build dependencies are listed in the distribution's Waybar PKGBUILD.
set -euo pipefail
scripts_dir=$(dirname "$(readlink -f "$0")")
cache="${XDG_CACHE_HOME:-$HOME/.cache}/waybar-hypr57"
meson_cmd="${MESON:-meson}"
command -v "$meson_cmd" >/dev/null
command -v gdbus-codegen >/dev/null
mkdir -p "$cache"
archive="$cache/source.tar.gz"
if [ ! -f "$archive" ]; then
  curl --fail --location --retry 2 --max-time 120 \
    https://github.com/Alexays/Waybar/archive/refs/tags/0.15.0.tar.gz -o "$archive"
fi
printf '%s  %s\n' '21c2bbef88c40473c355003582f9331d2f9b8a01efdcce0935edfc5f6b023a3e' "$archive" | sha256sum -c -
tar -xzf "$archive" -C "$cache"
patch -d "$cache/Waybar-0.15.0" -p1 < "$scripts_dir/waybar-patches/hyprland-057-workspace-clicks.patch"
"$meson_cmd" setup --wipe "$cache/build" "$cache/Waybar-0.15.0" \
  --buildtype=release -Dtests=disabled -Dman-pages=disabled -Dcava=disabled -Drfkill=enabled
ninja -C "$cache/build" -j "${BUILD_JOBS:-4}"
mkdir -p "$HOME/.local/libexec"
install -m 755 "$cache/build/waybar" "$HOME/.local/libexec/waybar-hypr57.new"
mv "$HOME/.local/libexec/waybar-hypr57.new" "$HOME/.local/libexec/waybar-hypr57"
printf 'Installed %s\n' "$HOME/.local/libexec/waybar-hypr57"
