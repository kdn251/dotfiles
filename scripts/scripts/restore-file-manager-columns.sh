#!/usr/bin/env bash
# Run inside your desktop session, with Thunar closed so it cannot overwrite widths.
set -euo pipefail

if pgrep -x thunar >/dev/null || pgrep -x Thunar >/dev/null; then
  echo 'Close Thunar first (including its background process: thunar --quit), then rerun.' >&2
  exit 1
fi

set_thunar() {
  local property=$1 type=$2 value=$3
  if xfconf-query -c thunar -p "$property" >/dev/null 2>&1; then
    xfconf-query -c thunar -p "$property" -s "$value"
  else
    xfconf-query -c thunar -p "$property" -n -t "$type" -s "$value"
  fi
}

columns='THUNAR_COLUMN_NAME,THUNAR_COLUMN_SIZE,THUNAR_COLUMN_TYPE,THUNAR_COLUMN_DATE_MODIFIED'
set_thunar /last-details-view-column-order string "$columns"
set_thunar /last-details-view-visible-columns string "$columns"
set_thunar /last-details-view-fixed-columns bool true
# Thunar 4.20 column enum order; name=330, size=85, type=170, modified=155.
set_thunar /last-details-view-column-widths string '50,50,155,123,92,200,50,50,330,50,50,85,50,170'
set_thunar /last-view string ThunarDetailsView
set_thunar /last-window-width int 1100
set_thunar /last-window-height int 750

if gsettings list-schemas | grep -qx org.gnome.nautilus.list-view; then
  gsettings set org.gnome.nautilus.preferences default-folder-viewer 'list-view'
  gsettings set org.gnome.nautilus.list-view default-visible-columns "['name', 'size', 'type', 'date_modified']"
  gsettings set org.gnome.nautilus.list-view default-column-order "['name', 'size', 'type', 'date_modified', 'owner', 'group', 'permissions', 'mime_type', 'where', 'date_modified_with_time', 'date_accessed', 'date_created', 'recency', 'starred']"
fi

echo 'Saved file-manager columns: Name, Size, Type, Date Modified.'
