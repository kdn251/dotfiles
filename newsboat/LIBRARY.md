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
(up to 200 comments, ten levels deep). If Reddit blocks its JSON endpoint,
downloads fall back to Reddit’s RSS discussion feed (up to 200 comments).
RSS comments appear in feed order with authors and original comment links;
Reddit does not provide reply nesting or scores there. Omitted replies are
labeled, and a download is reported as partial if both comment requests fail.
Use **Open original** for the complete, current discussion.

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

## Favorites

The  Favorites row appears above All. Use `f` to save an item for the long term and `F` to remove it; `U` undoes either action. Favorited items show  on their rows, with the heart first in Favorites. The home row shows the total saved count, including read items. Opening or reading an item does not remove it. Favorites keeps a local snapshot of its title, source, and feed content in `~/.local/state/newsboat/favorites.db`, independent of feed retention, Starred, and Commentary. It does not download the linked page/video or sync to Miniflux/Capy.

## Scheduled Twitch VODs

The 🎬 VODs row sits directly above Favorites and shows the total available files from `~/Videos/newsboat/twitch-vods` (excluding the `manual/` subdirectory used by `,d`). It inventories existing files independently of the RSS cache, with streamer names, titles, row numbers, watched percentages, and newest downloads first. The main-screen total counts completed and active VODs together (each VOD once), and updates while you remain on the main screen. Active downloads appear first with a live download counter; abandoned partial files are excluded.

Use `o`, `O`, or `,v` to play a local VOD. `,D` deletes the file and immediately removes its row, selecting the next remaining item. The scheduled downloader's archive is preserved so deleting a VOD does not cause that same latest VOD to be downloaded again. VODs opens immediately from its saved inventory, adding currently running scheduled downloads. Inventory checks run in the background when the view opens, at Newsboat startup, and after the scheduled downloader or pruning script updates the files. Unchanged invalid files are not repeatedly probed. Active rows update every two seconds: download percentage when the total duration is known, otherwise MB/GB downloaded. Playback and deletion of unfinished VODs are blocked. Reopen the list to pick up newly started downloads or refreshed inventory.

## 🍀 Random Starred pick

Press **7** on the main feed screen to open a random Starred item in the usual
Brave article window or mpv player. Newsboat remains usable. When that window
closes, a prompt inside Newsboat offers **u: Unstar** or **k: Keep starred**.
Enter or Escape also keeps it starred. The main-screen footer displays
**7: 🍀 Random Starred**. Unstarring uses the normal Miniflux sync queue,
so the change also reaches Capy. Only one random pick is active at a time.
Article window tracking uses Hyprland; failed or unconfirmed opens never unstar
an item. Restart Newsboat after installing this shortcut.

## Copy an item URL

Press **Ctrl+C** on a selected item in an article list or search results, or
while reading an article inside Newsboat, to copy its original web URL to the
Wayland clipboard. This also works for downloaded videos/articles and saved
lists; it copies the original link, not a local file path. Copying does not
open the item, move the selection, or mark it read. In a search/command input,
Ctrl+C cancels that input. This binding applies inside Newsboat.

In mpv opened through Newsboat, **Ctrl+C** copies the original video/stream URL
and shows “Video URL copied” without closing or pausing playback. The URL stays
the same after switching to a downloaded file. Reopen an existing player to
load this shortcut.

## Starred reading and watching progress

Starred shows a watched/read percentage beside each row number, using the same
progress records as Downloads. Rows sort by progress descending (including
100% completed items), then by publication date newest first. Untouched items
appear below items with progress. Live updates keep the same item selected.
Video resume positions are stored by video ID
so reopening a stream or its downloaded file returns to the same place.
Older saved percentages can also supply a resume position once duration is known.
Completed videos restart when reopened.

Opening an article with `o`/`O` from Starred registers its original URL for
browser-side reading progress. It opens the original website without downloading
anything, unless you already explicitly downloaded a copy (then the resumable
local reader still opens). The local Brave extension saves the furthest reading
percentage and latest scroll position, and restores the paragraph on reopening.
Scrolling with Vimium `j`/`k` is tracked even when Vimium consumes the key event.
Website and offline-reader anchors are kept separately because their layouts differ.
Only URLs registered by Newsboat are tracked; data stays on this computer.
Dynamic layouts can make positioning approximate. Reading percentage measures
scroll progress through the article, not whether its text was actually read.

Install on another machine with `python3 ~/scripts/newsboat-install-browser-reading.py`,
then fully quit and reopen Brave. This registers a native messaging host and adds
`newsboat/browser-extension` to `brave-flags.conf`. No browser profile reset is needed.
Restarting only Newsboat does not reload the browser extension. Registration matches
Reddit's old/www URL variants. Other redirected URLs currently need to match the
registered article URL to be tracked.

## Visual row selection and bulk undo

In an article list or search results, `V` starts visual-line selection at the
current row. `j`/`k` (and page navigation) extend or shrink the continuous range.
Selected rows use the existing teal highlight; the list title stays unchanged. `Esc`, `V`, or `q` cancel selection; another `q` then leaves the list.
Live progress updates do not reorder a range while it is being selected.

Use the existing actions on the range: `s`/`S` star/unstar, `f`/`F`
favorite/unfavorite, `c`/`C` add/remove Commentary, `n`/`N` toggle read status,
and `,D` delete downloaded copies. Each unique URL is acted on once. The
selection clears after the operation and the cursor moves to the next surviving
row after the range, or the preceding row at the end. Other commands, such as
opening an item or searching, clear selection and retain their normal behavior.

`U` reverses a whole bulk change, including file deletion, in one operation.
The undo journal keeps the last 100 actions (a batch counts as one), shared across
views in the current session. To make bulk `,D` reversible, files and sidecars
are moved into a recovery directory next to the video library instead of erased
immediately. They are permanently removed when the Newsboat session exits;
use `U` before quitting to restore them. Single-row `,D` outside visual mode
retains its existing immediate-delete behavior. Undo refuses to overwrite a
new file at the old location. An interrupted/rejected batch keeps completed
changes undoable.

Search checks titles, article contents, and author/source labels. Starred's
channel names are stored as source labels, so `/` can now find those as well as
read and unread article titles. Visual selection also works in search results.

## Reconnecting after suspend

Local query updates (including saved-list changes, Downloads reloads, and file
undo) reuse the current Miniflux subscription list. They do not synchronously
request `/v1/categories` and `/v1/feeds` on the UI thread. Explicit `R` still
retrieves the current subscriptions before starting the background feed refresh.
If that subscription request fails, the known list remains available; a valid
empty response still removes subscriptions normally.

Miniflux connections have a three-second connection timeout, discard connections
idle for more than ten seconds, and use TCP keepalives. The configured total
request timeout is eight seconds instead of the default thirty. These limits
bound stalled requests while Wi-Fi or Tailscale recovers. They do not change
the fifteen-minute automatic refresh interval.

The home screen's New count reads the current unread, non-deleted items in source
feeds, excluding aggregate query feeds. It updates as each feed finishes, instead
of waiting for the New query to rebuild at the end of the whole refresh.

Aggregate query lists, Starred and searches show each exact destination URL once. Different URLs remain separate even with identical titles. Reading a destination updates its loaded source copies together, including undo; New and All unread counts use unique URLs. Individual source feeds remain available.

Downloads includes unfinished attempts as soon as preparation starts. Active, failed and cancelled attempts sort above completed files; retry with `,d`. Finished files keep their watched-percentage/download-date order. Deleting an attempt removes its row.

## Books

The 📚 Books home row sits below VODs and inventories PDFs and EPUBs in `~/Books`, including subfolders. Set `NEWSBOAT_BOOKS_DIR` to override the folder. The home row shows a total count; the list shows filenames and formats, with currently reading books first, unopened books next, and finished books last (reading progress descending within the first group). Enter, o or O launches PDFs in Zathura and EPUBs in Foliate without blocking Newsboat; q returns home, / searches. Reopen Books to pick up filesystem changes (or run `python3 ~/scripts/newsboat-books.py rebuild` to update the home count). Files remain in their original folder and are never deleted by download cleanup. Books uses its own local view with no feed download/delete/star actions.

Browser reading progress recognizes HTTP/HTTPS and www/bare-host aliases while keeping paths, queries, and explicit ports distinct. Older registrations retain their original article ID and saved position, so redirected pages such as Paul Graham essays update the original Starred row. The native host change applies on the next message; reopen an already-untracked tab to initialize tracking.

Books polls reader-owned state every two seconds while its list is open. Zathura supplies the current PDF page over D-Bus and saves position/zoom in its own SQLite database. Foliate supplies EPUB location/progress through its native JSON state. Newsboat stores the furthest percentage reached in `~/.local/state/newsboat/books/progress.json`; reopening uses the reader’s last position, even if you went backwards. Percentages represent page/location progress, not proof of reading. The selected book stays selected as progress reorders rows. Foliate is listed in `pacman-packages.txt`. PDF progress requires `pdfinfo` and Python GObject bindings, already installed here.
