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

## Offline articles

Use `,d` on an HTTP article to save a clean, dark reading page. The download
runs in the background and shares the existing notifications, Waybar status,
row badge, and Downloads list. `o` or `O` opens the saved HTML in Brave while
history records the original article URL. `,D` deletes the saved copy.

Text and supported images are stored in one HTML file under
`~/Videos/newsboat/articles`. Links remain clickable and an **Open original**
link appears above the article. The original site's layout, scripts, and embedded players are not preserved.
Reddit comments are handled separately as described below. Short extracts and recognized paywall
prompts fail with an explanation; other extraction omissions cannot always be
detected. Missing images are marked in the saved page and completion notice.
Articles are not subject to the watched-video automatic cleanup policy.

On another machine, run `~/scripts/newsboat-article-setup.sh` once to install
Trafilatura in an isolated Python environment. Article downloads do not use
browser cookies or unlock subscription content.

Reddit post downloads use the post body cached by Newsboat (or its Starred
snapshot). Crossposts resolve to the original post, using its RSS entry if
necessary. Link-only feed entries are rejected when the original body cannot
be obtained; they are never reported as complete downloads. Short posts do
not fail the article-length check and Reddit's JavaScript page is not required. Downloads also request a snapshot of the top comments and nested replies
(up to 200 comments, ten levels deep). They label omitted replies and report
blocked comment requests as a partial copy. Use **Open original** for the
complete, current discussion.

Saved pages provide their own keyboard shortcuts: `j`/`k` scroll smoothly (including
held keys), `gg`/`G` go
to the beginning/end, `Ctrl+d`/`Ctrl+u` scroll half a page, and `q` closes the
reading window. Reload an already open page after a shortcut update. Only the
bundled keyboard script is allowed by the saved page's content security policy;
scripts from the original article remain removed.

Downloads retain their row order while deletion updates are applied, so `,D`
selects the next remaining row (or the preceding row at the end of the list).
Restart Newsboat after installing the native deletion-order fix.

Downloaded articles now show reading progress in the same column as video
watch progress. This estimates progress from scrolling through the article;
it does not measure comprehension. The percentage keeps the furthest point
reached, while the saved position records the most recent location. Reddit
comments do not contribute to the post percentage, but positions inside them
are still restored.

Open a downloaded article with `o`/`O` to use the local reader. It starts a
small Python HTTP service bound only to 127.0.0.1, serving registered downloads
under a random access token. No internet connection is required. Positions
are saved during scrolling and on exit; `q` saves before closing. Reopening
restores the paragraph and offset after images load. Existing saved files
also work without downloading them again. Opening the HTML directly from a
file manager does not use this tracking service.

Reading state is stored in `~/.local/state/newsboat/reading-progress.db` and
published to `download-status.tsv.read`. It is separate from video progress
and watched-video cleanup. Restart Newsboat after installing the native
article-progress patch; reopen an article from Newsboat to enable tracking.
