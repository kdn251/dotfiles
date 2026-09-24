#!/bin/sh
# Install the article extractor without changing the system Python packages.
set -eu
venv="${XDG_DATA_HOME:-$HOME/.local/share}/newsboat/article-venv"
python3 -m venv "$venv"
"$venv/bin/pip" install 'trafilatura==2.0.0'
