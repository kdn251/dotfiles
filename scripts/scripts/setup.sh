#!/usr/bin/env bash
# Public bootstrap: deploy this file to https://k2.codes/setup.sh.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo 'Usage: bash setup.sh [--check | --desktop] (Arch Linux, regular knaught user)'
  exit 0
fi
[[ $EUID -ne 0 ]] || { echo 'Run as your normal sudo-enabled user, not root.' >&2; exit 1; }
repo="$HOME/dotfiles"
# A local invocation must use this checkout, including unpublished changes.
if [[ -n ${BASH_SOURCE[0]:-} && -f ${BASH_SOURCE[0]} ]]; then
  source_path=$(readlink -f "${BASH_SOURCE[0]}")
  candidate=$(dirname "$source_path")/../..
  if [[ -f $candidate/bootstrap/restore.sh ]]; then
    repo=$(cd "$candidate" && pwd)
  fi
fi
if [[ ! -d $repo/.git ]]; then
  [[ ! -e $repo ]] || { echo "$repo exists but is not a Git checkout; reconcile it first." >&2; exit 1; }
  [[ ${1:-} != --check ]] || { echo 'Clone the repository before running --check.' >&2; exit 1; }
  sudo pacman -Syu --needed git python
  git clone https://github.com/kdn251/dotfiles.git "$repo"
fi
# Never move an existing checkout or silently pull over local work.
exec bash "$repo/bootstrap/restore.sh" "$@"
