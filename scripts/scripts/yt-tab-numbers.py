#!/usr/bin/env python3
"""Number the YouTube webapp tabs 1..N, left to right in the groupbar.

Hyprland's groupbar renders a window's title and offers no per-tab label
option, so the numbers come from setting document.title over CDP.

Ordering is the tricky part: CDP lists targets in creation order, which is NOT
the order the tabs sit in the bar. Hyprland knows the visual order (the group
member list) but has no idea which CDP target belongs to which window. So this
runs in two phases -- stamp every target with a unique token, read back which
window carries which token to build the mapping, then write the final numbers
in group order. The stamp is invisible (see STAMP_JS) so the groupbar never
shows it while a tab is being added or closed.

The keeper (MutationObserver on <title>) re-applies the number because YouTube
rewrites the title on every in-page navigation. It lives in the page, so a
reload drops it until this runs again.
"""

import fcntl
import importlib.util
import json
import os
import subprocess
import sys
import time

_spec = importlib.util.spec_from_file_location(
    "cdp", os.path.expanduser("~/scripts/yt-pip-cdp.py"))
cdp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cdp)

SET_JS = """
(() => {
  const n = %r;
  if (window.__ytTabNum) { window.__ytTabNum.disconnect(); }
  document.title = n;
  const t = document.querySelector('title');
  if (t) {
    window.__ytTabNum = new MutationObserver(() => {
      if (document.title !== n) document.title = n;
    });
    window.__ytTabNum.observe(t, {childList: true});
  }
  return n;
})()
"""

# Phase-1 stamp. The groupbar renders whatever the title happens to be, and
# there is a ~0.6 s gap before phase 2 lands, so the stamp must not be visible
# -- it used to read "yt~0~". It keeps the title the tab already shows and
# appends k zero-width spaces, which render as nothing but survive the trip
# through Brave, Wayland and the compositor intact (verified: hyprctl reports
# them byte for byte, and str.strip() leaves them alone since Python does not
# class U+200B as whitespace). Uniqueness rides entirely on k, so the visible
# part is free to be whatever is least jarring. Trailing ZWSPs left by an
# interrupted earlier run are dropped first, so k stays the only variable.
STAMP_JS = r"""
(() => {
  const k = %d;
  if (window.__ytTabNum) { window.__ytTabNum.disconnect(); }
  const base = (document.title || '').replace(/\u200b+$/, '') || 'YouTube';
  const n = base + '\u200b'.repeat(k);
  document.title = n;
  const t = document.querySelector('title');
  if (t) {
    window.__ytTabNum = new MutationObserver(() => {
      if (document.title !== n) document.title = n;
    });
    window.__ytTabNum.observe(t, {childList: true});
  }
  return n;
})()
"""

ZWSP = "\u200b"


def evaluate(target, js):
    """Run js in the page, returning its value (None if the call failed)."""
    ws = cdp.WS(target["webSocketDebuggerUrl"])
    try:
        ws.send({"id": 1, "method": "Runtime.evaluate",
                 "params": {"expression": js, "returnByValue": True}})
        for _ in range(20):
            msg = ws.recv()
            if msg.get("id") == 1:
                return msg.get("result", {}).get("result", {}).get("value")
    finally:
        ws.close()
    return None


def clients():
    out = subprocess.run(["hyprctl", "clients", "-j"],
                         capture_output=True, text=True, timeout=5).stdout
    return json.loads(out or "[]")


def main():
    # The watcher can fire several times in a burst (a window open emits more
    # than one event). Overlapping runs corrupt the token mapping, so only one
    # proceeds; the others exit and let it finish.
    lock_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
                             "yt-tab-numbers.lock")
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0

    try:
        try:
            targets = [t for t in cdp.targets()
                       if t.get("type") == "page" and "youtube.com" in t.get("url", "")]
        except Exception as exc:
            print("cannot reach DevTools: %s" % exc, file=sys.stderr)
            return 2
        if not targets:
            return 0

        # Phase 1: unique token per target, so each window can be identified.
        # Key off the string the page reports back rather than rebuilding it
        # here: the base is whatever the tab was already showing, which only
        # the page knows.
        tokens = {}
        for i, t in enumerate(targets):
            tok = evaluate(t, STAMP_JS % (i + 1))
            if isinstance(tok, str):
                tokens[tok] = t
        time.sleep(0.6)   # let the titles propagate to the compositor

        # Phase 2: walk the group in visual order and number accordingly.
        cs = clients()
        cls = lambda c: c.get("class") or ""
        # "music.youtube.com" also contains "youtube.com"; the music PWA is a
        # separate app and is never part of these tabs.
        yt = [c for c in cs if "youtube.com" in cls(c) and "music." not in cls(c)]
        ordered = []
        grouped = next((c.get("grouped") or [] for c in yt if c.get("grouped")), [])
        if grouped:
            by_addr = {c.get("address"): c for c in yt}
            ordered = [by_addr[a] for a in grouped if a in by_addr]
        if not ordered:
            # Not grouped (a single window, or grouping off): fall back to x position.
            ordered = sorted(yt, key=lambda c: (c.get("at") or [0, 0])[0])

        n = 0
        for c in ordered:
            t = tokens.get((c.get("title") or "").strip())
            if not t:
                continue
            n += 1
            evaluate(t, SET_JS % str(n))

        # Safety sweep: a token must never be left showing as a window title.
        # Titles are read back over CDP rather than from hyprctl -- an earlier
        # version asked the compositor immediately after writing and raced it,
        # seeing already-numbered tabs as unnumbered and renumbering them 3, 4.
        for t in targets:
            try:
                ws = cdp.WS(t["webSocketDebuggerUrl"])
            except Exception:
                continue
            try:
                ws.send({"id": 1, "method": "Runtime.evaluate",
                         "params": {"expression": "document.title",
                                    "returnByValue": True}})
                title = None
                for _ in range(20):
                    msg = ws.recv()
                    if msg.get("id") == 1:
                        title = msg.get("result", {}).get("result", {}).get("value")
                        break
            finally:
                ws.close()
            # A real page title never ends in a zero-width space, so this
            # only ever catches a stamp phase 2 failed to overwrite.
            if isinstance(title, str) and title.endswith(ZWSP):
                n += 1
                evaluate(t, SET_JS % str(n))

        print("numbered %d tab(s) in group order" % n)
        return 0
    finally:
        try:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
