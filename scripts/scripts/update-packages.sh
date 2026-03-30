#!/bin/bash

# =========================================================
# Configuration
# =========================================================
REPO_DIR="$HOME/dotfiles"
AUR_FILE="$REPO_DIR/aur-packages.txt"
PACMAN_FILE="$REPO_DIR/pacman-packages.txt"
LOG_FILE="$HOME/.local/state/package-backup.log"

mkdir -p "$REPO_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

echo "[$(date)] Starting package list update..." >>"$LOG_FILE"

# =========================================================
# 1. NEW: Cleanup Orphans (This was missing!)
# =========================================================
# Check for and remove orphans
if pacman -Qdtq >/dev/null 2>&1; then
  echo "[$(date)] Found orphans, removing..." >>"$LOG_FILE"
  sudo pacman -Rs $(pacman -Qdtq) --noconfirm >>"$LOG_FILE" 2>&1
fi

# Clean AUR orphans
yay -Yc --noconfirm >>"$LOG_FILE" 2>&1

# =========================================================
# 2. Update package lists
# =========================================================
# Native (Pacman) explicitly installed
pacman -Qen | awk '{print $1}' | grep -v "^steam$" >"$PACMAN_FILE"

# Foreign (AUR) explicitly installed
pacman -Qem | awk '{print $1}' |
  grep -vE "^davinci-resolve$|^paru$|-debug$|^tzupdate$|^localsend$" |
  sed 's/^voxtype$/voxtype-bin/' >"$AUR_FILE"

# =========================================================
# 3. Git Operations
# =========================================================
cd "$REPO_DIR" || exit 1

if [[ -n $(git status --porcelain) ]]; then
  git add "$AUR_FILE" "$PACMAN_FILE"
  COMMIT_MSG="Auto-update package lists: $(date +'%Y-%m-%d %H:%M')"
  git commit -m "$COMMIT_MSG"

  if git push origin main; then
    echo "[$(date)] SUCCESS: Changes pushed to GitHub." >>"$LOG_FILE"
    notify-send "Package Backup" "Success: System cleaned and pushed."
  else
    echo "[$(date)] ERROR: Git push failed." >>"$LOG_FILE"
  fi
else
  echo "[$(date)] No changes detected in lists. Skipping push." >>"$LOG_FILE"
fi
