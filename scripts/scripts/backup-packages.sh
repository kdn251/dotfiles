#!/bin/bash
DOTFILES_DIR="$HOME/dotfiles"

pacman -Qqen >"$DOTFILES_DIR/pacman-packages.txt"
pacman -Qqem >"$DOTFILES_DIR/aur-packages.txt"

cd "$DOTFILES_DIR" || exit 1

if git diff --quiet pacman-packages.txt aur-packages.txt; then
  exit 0
fi

git add pacman-packages.txt aur-packages.txt
git commit -m "update package lists ($(date '+%Y-%m-%d %H:%M'))"
git push
