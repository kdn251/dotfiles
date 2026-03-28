#!/bin/bash

# =========================================================
# Configuration
# =========================================================
# Ensure this is the absolute path to your local git repository
REPO_DIR="$HOME/dotfiles"
AUR_FILE="$REPO_DIR/aur-packages.txt"
PACMAN_FILE="$REPO_DIR/pacman-packages.txt"
LOG_FILE="$HOME/.local/state/package-backup.log"

# Ensure directories exist
mkdir -p "$REPO_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

# Start logging
echo "[$(date)] Starting package list update..." >>"$LOG_FILE"

# 1. Update package lists
# -Qen: Native (Pacman) explicitly installed
# -Qem: Foreign (AUR) explicitly installed
# Filter out 'steam' to prevent installation failures on systems without multilib enabled.
pacman -Qen | awk '{print $1}' | grep -v "^steam$" >"$PACMAN_FILE"

# Filter out 'davinci-resolve' and others to prevent unwanted heavy dependencies like qt5-location.
pacman -Qem | awk '{print $1}' |
  grep -vE "^davinci-resolve$|^paru$|-debug$|^tzupdate$|^localsend$" |
  sed 's/^voxtype$/voxtype-bin/' >"$AUR_FILE"

# 2. Git Operations
cd "$REPO_DIR" || {
  echo "[$(date)] Error: Could not enter $REPO_DIR" >>"$LOG_FILE"
  exit 1
}

# Check for changes
if [[ -n $(git status --porcelain) ]]; then
  git add "$AUR_FILE" "$PACMAN_FILE"

  COMMIT_MSG="Auto-update package lists: $(date +'%Y-%m-%d %H:%M')"
  git commit -m "$COMMIT_MSG"

  # Push to GitHub (Assumes SSH key is configured)
  if git push origin main; then
    echo "[$(date)] SUCCESS: Changes pushed to GitHub." >>"$LOG_FILE"
    notify-send "Package Backup" "Successfully pushed updated package lists to GitHub."
  else
    echo "[$(date)] ERROR: Git push failed." >>"$LOG_FILE"
    notify-send -u critical "Package Backup" "Failed to push to GitHub. Check $LOG_FILE"
  fi
else
  echo "[$(date)] No changes detected. Skipping push." >>"$LOG_FILE"
fi
