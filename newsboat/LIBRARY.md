# Starred and downloads

Newsboat starts on **⛵ Newsboat**, showing New, Starred, Downloads, and **📚 All**.
Open All to browse every individual feed source, including feeds with no unread
items. Press `q` from a source's article list to return to All, then `q` again
to return Home. All feeds continue to refresh and contribute to New as before.

The article list displays download status beside each matching video: `↓ 42%`,
`…` while preparing/processing, `📥` when downloaded, and `✕` after a failure.
Starred items also display the yellow five-point star (`󰓎`); both badges appear when a video is starred and
downloaded. Updates appear once per second while the article list is open.
Downloads counts refresh automatically when the library changes, including
while the main feed list is idle, without moving the selection. This uses the
local native build; rebuild with `~/scripts/newsboat-build-paged.sh` after
installing this setup on another machine. Restart Newsboat after upgrading.

## Starred on desktop and phone

Open **⭐ Starred** from the main Newsboat screen. `s` stars an item and `S`
unstars it. The row badge confirms success without a desktop notification. Capy Reader's **Starred** section uses the same Miniflux collection.
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

## YouTube sign-in challenges

If anonymous extraction receives YouTube's “not a bot” sign-in challenge, the
downloader retries once using Brave's existing session with GNOME Keyring and
uses the same session for the download. Cookies are not exported to a file.
`NEWSBOAT_YOUTUBE_BROWSER` can override `brave+gnomekeyring`. Other failures and
Twitch downloads do not trigger this authentication fallback.
