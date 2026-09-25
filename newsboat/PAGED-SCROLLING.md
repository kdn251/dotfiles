# Centered scrolling

The launcher uses `~/.local/lib/newsboat-paged/newsboat` for the custom collection
features. Lists now use Newsboat's built-in `scrolloff 999`: the selection stays
in the middle of the available list area, with rows above and below it, except
near the beginning/end or in a short list. The visible context adapts to terminal
height. History, Starred, Commentary, Favorites, VODs, and offline Downloads use
the same setting.

The launcher clears the old `NEWSBOAT_PAGE_SCROLL` override. The optional paging
patch remains available in the build, but is inactive in normal sessions.

Build or reinstall with `~/scripts/newsboat-build-paged.sh` (requires Newsboat's
C++/Rust build dependencies). The source download is pinned by SHA-256. The system
Newsboat package is unchanged.
