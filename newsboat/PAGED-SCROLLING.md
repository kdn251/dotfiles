# Page scrolling

The launcher uses `~/.local/lib/newsboat-paged/newsboat` when installed. This is
Newsboat r2.44 with the opt-in patch in `patches/paged-lists.patch`.

With `NEWSBOAT_PAGE_SCROLL=1`, list selection crosses screen boundaries by
whole pages. The next item is at the top, including on a short final page.
Moving up crosses to the previous page. Article text scrolling is unchanged.
Shelf and History inherit the same behavior.

Build or reinstall with `~/scripts/newsboat-build-paged.sh` (requires Newsboat's
C++/Rust build dependencies). The download is pinned by SHA-256. The system
Newsboat package is unchanged. Remove the local binary to use it again.
