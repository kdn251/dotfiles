#!/usr/bin/env python3
"""Toggle Picture-in-Picture in the YouTube webapp via the DevTools protocol.

Calls the actual API the context-menu item calls:

    document.pictureInPictureElement
      ? document.exitPictureInPicture()
      : document.querySelector('video').requestPictureInPicture()

with userGesture:true, which satisfies the user-activation requirement that
synthetic keystrokes could not.

Requires the isolated profile launched by ~/scripts/yt-webapp.sh, which
opens a loopback DevTools port. Never enable this on the main Brave profile.

The WebSocket client is hand-rolled because python-websockets is not
installed; CDP needs only a single text frame and one reply.
"""

import base64
import html
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

PORT = int(os.environ.get("BRAVE_CDP_PORT", "9222"))
HOST = "127.0.0.1"
MATCH = os.environ.get("YT_PIP_MATCH", "youtube.com")

# Use YouTube's own player API, not video.playbackRate directly. Setting the
# element fights the player: it re-asserts its stored speed a moment later, so
# the change appears to take and then silently reverts. setPlaybackRate updates
# the player's own state, so it sticks (and the speed menu reflects it).
# Falls back to the raw element for any page without the YouTube player.
VIDEO_JS = """
  const p = document.getElementById('movie_player');
  const vids = [...document.querySelectorAll('video')].filter(v => v.readyState > 0);
  const v = document.pictureInPictureElement ||
    (p && p.querySelector('video')) || vids.find(v => !v.paused && !v.ended) || vids[0];
"""

RATE_JS = "(() => {" + VIDEO_JS + """
  if (!v) return 'no-video';
  const rate = %s;
  if (p && typeof p.setPlaybackRate === 'function') p.setPlaybackRate(rate);
  // Verify the actual media element, including the one rendered in PiP.
  if (v.playbackRate !== rate) v.playbackRate = rate;
  return v.playbackRate;
})()
"""

STATE_JS = "(() => {" + VIDEO_JS + """
  return {title: document.title, pip: !!document.pictureInPictureElement,
          video: !!v, playing: !!v && !v.paused && !v.ended,
          rate: v ? v.playbackRate : null};
})()
"""


def set_rate(target, rate):
    # Poll from Python: timers inside background pages can be throttled.
    # A successful API call alone does not mean YouTube accepted the rate.
    for attempt in range(3):
        result = probe(target, RATE_JS % rate)
        if result == 'no-video':
            time.sleep(0.2)
            continue
        for _ in range(3):
            time.sleep(0.15)
            state = probe(target, STATE_JS) or {}
            if state.get('rate') != rate:
                break
        else:
            print('%gx' % rate)
            return 0
    print('YouTube did not accept the requested playback speed', file=sys.stderr)
    return 1


TOGGLE_JS = """
(() => {
  if (document.pictureInPictureElement) {
    document.exitPictureInPicture();
    return 'exited';
  }
  const vids = [...document.querySelectorAll('video')]
    .filter(v => v.readyState > 0);
  // Prefer the one actually playing; YouTube keeps hidden preview videos around.
  const v = vids.find(x => !x.paused) || vids[0];
  if (!v) return 'no-video';
  v.requestPictureInPicture();
  return 'entered';
})()
"""


def targets():
    with urllib.request.urlopen("http://%s:%d/json" % (HOST, PORT), timeout=3) as r:
        return json.load(r)


def webapp_title():
    """Title of the app-mode window, used to disambiguate.

    There can be several youtube.com pages open (a normal tab as well as the
    webapp), and CDP does not say which is app-mode. The webapp window's title
    tracks its page title, so hyprctl gives a reliable link.

    With tabs there are several webapp windows and the right one is the group's
    ACTIVE tab, which is not the same thing as the focused window. Requiring
    focusHistoryID == 0 meant the hotkeys only worked while the webapp itself
    had focus; from any other window nothing matched and an arbitrary tab was
    used instead. Hyprland reports hidden=false for every group member, so the
    active tab cannot be read directly -- it is the most recently focused one,
    the LOWEST focusHistoryID. That is the focused window when the webapp has
    focus and stays correct after focus moves away.
    """
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"],
                             capture_output=True, text=True, timeout=3).stdout
        clients = json.loads(out or "[]")
        # "music.youtube.com" contains "youtube" too; the music PWA is a
        # separate app and must never be targeted by these hotkeys.
        yt = [c for c in clients
              if "youtube.com" in (c.get("class") or "")
              and "music." not in (c.get("class") or "")]
        if not yt:
            return ""
        best = min(yt, key=lambda c: (c.get("focusHistoryID", -1) if c.get("focusHistoryID", -1) >= 0 else 1 << 30))
        return (best.get("title") or "").strip()
    except Exception:
        pass
    return ""


def probe(t, expr):
    """Evaluate a tiny expression on one page, returning None on any trouble.

    Used to ask pages about themselves while choosing between them, so it must
    never raise: a tab that is slow or gone should just drop out of the running.
    """
    try:
        ws = WS(t["webSocketDebuggerUrl"])
    except Exception:
        return None
    try:
        ws.send({"id": 1, "method": "Runtime.evaluate",
                 "params": {"expression": expr, "returnByValue": True}})
        for _ in range(20):
            msg = ws.recv()
            if msg.get("id") == 1:
                return msg.get("result", {}).get("result", {}).get("value")
    except Exception:
        return None
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return None


def pick(ts):
    # Parse the host: substring matching also caught YouTube Music and URLs
    # that merely mention youtube.com. Probe every page BEFORE URL ranking:
    # Shorts, live pages and SPA navigation can all hold the PiP video.
    hosts = {"youtube.com", "www.youtube.com", "m.youtube.com"}
    pages = [t for t in ts if t.get("type") == "page"
             and urllib.parse.urlparse(t.get("url", "")).hostname in hosts]
    states = [(t, probe(t, STATE_JS)) for t in pages]
    states = [(t, state) for t, state in states if isinstance(state, dict)]
    for t, state in states:
        if state.get("pip"):
            return t
    playing = [(t, state) for t, state in states if state.get("playing")]
    if len(playing) == 1:
        return playing[0][0]
    want = webapp_title().rstrip("\u200b")
    candidates = playing or states
    if want:
        for t, state in candidates:
            # Live document titles avoid stale /json metadata during numbering.
            title = html.unescape(state.get("title", "")).strip().rstrip("\u200b")
            if title == want and state.get("video"):
                return t
    for t, state in candidates:
        if state.get("video"):
            return t
    return states[0][0] if states else None


class WS:
    """Minimal RFC6455 client: handshake, one masked text frame, read replies."""

    def __init__(self, url):
        path = url.split(HOST + ":%d" % PORT, 1)[1]
        self.s = socket.create_connection((HOST, PORT), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, HOST, PORT, key)
        )
        self.s.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.s.recv(4096)
            if not chunk:
                raise RuntimeError("handshake closed early")
            buf += chunk
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError("handshake refused: %s" % buf.split(b"\r\n", 1)[0])
        self.buf = buf.split(b"\r\n\r\n", 1)[1]

    def send(self, obj):
        data = json.dumps(obj).encode()
        hdr = bytearray([0x81])           # FIN + text
        n = len(data)
        mask_bit = 0x80
        if n < 126:
            hdr.append(mask_bit | n)
        elif n < 65536:
            hdr.append(mask_bit | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(mask_bit | 127)
            hdr += struct.pack(">Q", n)
        m = os.urandom(4)
        hdr += m
        self.s.sendall(bytes(hdr) + bytes(b ^ m[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise RuntimeError("connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        b0, b1 = self._read(2)
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._read(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._read(8))[0]
        if b1 & 0x80:                      # server frames are never masked
            self._read(4)
        return json.loads(self._read(n).decode())

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def main():
    try:
        ts = targets()
    except Exception as exc:
        print("cannot reach DevTools on %s:%d (%s)" % (HOST, PORT, exc), file=sys.stderr)
        return 2

    t = pick(ts)
    if not t:
        print("no %s page found" % MATCH, file=sys.stderr)
        return 3

    # `--rate N` sets playback speed instead of toggling PiP. Setting it on the
    # video element carries into the PiP window, since PiP renders the same
    # element rather than a copy.
    # `--open URL` navigates the existing webapp window instead of toggling
    # PiP. App-mode windows have no address bar, so this is how a link gets in
    # without spawning a second window.
    if len(sys.argv) > 2 and sys.argv[1] == "--open":
        ws = WS(t["webSocketDebuggerUrl"])
        try:
            ws.send({"id": 1, "method": "Page.navigate",
                     "params": {"url": sys.argv[2]}})
            for _ in range(20):
                msg = ws.recv()
                if msg.get("id") == 1:
                    err = msg.get("result", {}).get("errorText")
                    if err:
                        print(err, file=sys.stderr)
                        return 1
                    print("navigated")
                    return 0
            return 1
        finally:
            ws.close()

    expr = TOGGLE_JS
    if len(sys.argv) > 2 and sys.argv[1] == "--rate":
        return set_rate(t, float(sys.argv[2]))

    ws = WS(t["webSocketDebuggerUrl"])
    try:
        ws.send({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expr,
                "userGesture": True,        # the bit that makes PiP allowed
                "awaitPromise": True,
                "returnByValue": True,
            },
        })
        for _ in range(20):                 # skip unrelated events
            msg = ws.recv()
            if msg.get("id") == 1:
                res = msg.get("result", {})
                if "exceptionDetails" in res:
                    print(res["exceptionDetails"].get("text", "error"), file=sys.stderr)
                    return 1
                print(res.get("result", {}).get("value", "?"))
                return 0
        print("no reply", file=sys.stderr)
        return 1
    finally:
        ws.close()


if __name__ == "__main__":
    try:
        status = main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        status = 1
    if status and "--rate" in sys.argv:
        subprocess.run(["notify-send", "-a", "YouTube", "-t", "4000",
                        "YouTube speed",
                        "Could not change speed. Open a video using Mod+Shift+Y and try again."],
                       check=False)
    sys.exit(status)
