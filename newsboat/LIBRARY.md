# Starred and downloads

The article list displays download status beside each matching video: `↓ 42%`,
`…` while preparing/processing, `✓` when downloaded, and `✕` after a failure.
Updates appear once per second while the article list is open. This uses the
local native build; rebuild with `~/scripts/newsboat-build-paged.sh` after
installing this setup on another machine. Restart Newsboat after upgrading.

## Starred on desktop and phone

Open **⭐ Starred** from the main Newsboat screen. `s` stars an item and `S`
unstars it. Capy Reader's **Starred** section uses the same Miniflux collection.
Reading, opening or watching something does not unstar it on either device.
Both read and unread stars appear in the desktop view. `C` asks for confirmation
before unstarring all displayed items.

Miniflux is the sole saved collection: there is no separate Shelf database or
sync queue in use. The view fetches current stars when opened; reopen it to see
phone changes. Star/unstar actions require a connection and report failures.
The minute timer refreshes the main menu's query/count and protects starred
downloads during cleanup. Old Shelf data is retained locally as a backup only.
The duplicate built-in Starred Items row is hidden.

## Automatic cleanup

`~/.newsboat/download-cleanup.json` controls cleanup (`enabled`, `days`).
Default: remove a downloaded file seven days after mpv reaches 90% playback.
Only explicit downloads in `~/Videos/newsboat` qualify. Older downloads are
not assumed watched: tracking starts when they are played with this setup.
Unwatched videos, starred items, active downloads, files currently being
played, and replaced files are protected. A failed Miniflux request skips cleanup.
The grace period starts from the latest completed playback.

The user service `newsboat-maintenance.service` fetches Miniflux stars before cleanup.
Check it with `systemctl --user status newsboat-maintenance.timer` or
`journalctl --user -u newsboat-maintenance.service`. Disable all automatic
maintenance with `systemctl --user disable --now newsboat-maintenance.timer`.
Disable deletion alone by setting `enabled` to false in the JSON config.
