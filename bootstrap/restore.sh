#!/usr/bin/env bash
# Restore the public desktop configuration; see dotfiles.md for private state.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:---install}
case "$mode" in --install|--check|--desktop) ;; *) echo 'Usage: restore.sh [--install|--check|--desktop]' >&2; exit 2;; esac
[[ $# -le 1 ]] || exit 2
list() { sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$1"; }
mapfile -t packages < <(list "$repo/bootstrap/stow-packages.txt")
ignore=()
while read -r pattern; do ignore+=("--ignore=$pattern"); done < "$repo/bootstrap/stow-ignore.txt"
if [[ $mode == --check ]]; then
  exec python3 "$repo/bootstrap/check.py"
fi
[[ $EUID -ne 0 ]] || { echo 'Run as the regular user, not root.' >&2; exit 1; }
[[ $HOME == /home/knaught && $(id -un) == knaught ]] || {
  echo 'This desktop currently requires user knaught with HOME=/home/knaught. See dotfiles.md.' >&2; exit 1;
}
[[ $(uname -m) == x86_64 && -f /etc/arch-release ]] || { echo 'Requires x86_64 Arch Linux.' >&2; exit 1; }
[[ $repo == "$HOME/dotfiles" ]] || { echo 'Keep the checkout at ~/dotfiles for existing scripts.' >&2; exit 1; }
trap 'echo "Restore stopped at line $LINENO. Fix the error and rerun; no success was recorded." >&2' ERR
if [[ $mode == --desktop ]]; then
  [[ -n ${WAYLAND_DISPLAY:-} ]] || { echo 'Run --desktop inside Hyprland.' >&2; exit 1; }
  bash "$repo/scripts/scripts/restore-file-manager-columns.sh"
  python3 "$repo/agent-attention/.local/share/agent-attention/install.py"
  systemctl --user daemon-reload
  while read -r unit; do systemctl --user enable "$unit"; done < <(list "$repo/bootstrap/user-services.txt")
  echo 'Desktop preferences restored. Log out/in to start session services.'
  exit 0
fi
sudo -v
# Steam and the existing 32-bit graphics packages require multilib.
if ! pacman-conf --repo-list | grep -qx multilib; then
  echo 'Enable [multilib] with Include = /etc/pacman.d/mirrorlist in /etc/pacman.conf, then rerun.' >&2
  exit 1
fi
mapfile -t official < <(cat "$repo/pacman-packages.txt" <(list "$repo/bootstrap/packages.txt") | sort -u)
sudo pacman -Syu --needed "${official[@]}"
# Show all conflicts before changing any home configuration; never use --adopt.
stow "${ignore[@]}" --simulate --no-folding -d "$repo" -t "$HOME" "${packages[@]}"
if ! command -v yay >/dev/null; then
  work=$(mktemp -d)
  git clone https://aur.archlinux.org/yay.git "$work/yay"
  (cd "$work/yay" && makepkg -si --needed)
  rm -rf "$work"
fi
# Foreign packages are not necessarily downloadable AUR packages (e.g. debug output).
mapfile -t foreign < <(list "$repo/aur-packages.txt" | sed '/-debug$/d; /^yay$/d')
((${#foreign[@]} == 0)) || yay -S --needed "${foreign[@]}"
stow "${ignore[@]}" --no-folding -d "$repo" -t "$HOME" "${packages[@]}"
mkdir -p "$HOME/software" "$HOME/.local/state/obs-display-follow"
fc-cache -f
bash "$repo/scripts/scripts/build-waybar-hypr57.sh"
bash "$repo/scripts/scripts/newsboat-build-paged.sh"
bash "$repo/scripts/scripts/newsboat-article-setup.sh"
python3 "$repo/scripts/scripts/install-mpv-apple-emoji.py"
if pgrep -x obs >/dev/null; then echo 'Close OBS before rebuilding its bridge.' >&2; exit 1; fi
cc -shared -fPIC -Wall -Wextra -Werror -I/usr/include/obs \
  "$repo/scripts/scripts/obs-display-create.c" -o "$HOME/scripts/obs-display-create.so" -lobs
python3 "$repo/setup-pi.py"
python3 "$repo/agent-attention/.local/share/agent-attention/install.py" --no-start
sudo bash "$repo/bootstrap/system.sh" "$repo"
systemctl --user daemon-reload
while read -r unit; do systemctl --user enable "$unit"; done < <(list "$repo/bootstrap/user-services.txt")
if [[ $(getent passwd "$(id -un)" | cut -d: -f7) != /usr/bin/zsh ]]; then
  sudo chsh -s /usr/bin/zsh "$(id -un)"
fi
# Preserve unrelated jobs; do not activate source-machine auto-update/auto-push jobs.
python3 "$repo/bootstrap/cron.py"
echo 'Public desktop restore completed. Reboot, log into Hyprland, then run:'
echo '  bash ~/dotfiles/setup.sh --desktop'
echo 'Private app data, logins, Flatpaks and hardware checks: ~/dotfiles/dotfiles.md'
