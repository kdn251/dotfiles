#!/usr/bin/env python3
"""Toggle Picture-in-Picture in the YouTube webapp via the DevTools protocol.

Calls the actual API the context-menu item calls:

    document.pictureInPictureElement
      ? document.exitPictureInPicture()
      : document.querySelector('video').requestPictureInPicture()

with userGesture:true, which satisfies the user-activation requirement that
synthetic keystrokes could not.

Requires Brave started with --remote-debugging-port (set in
~/.config/brave-flags.conf). The port is read only at process startup, so a
full Brave restart is needed after adding it.

NOTE on the tradeoff: that port is unauthenticated and grants any local
process full control of the browser. It is open for the life of the browser,
not just while this script runs.

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
import urllib.request

PORT = int(os.environ.get("BRAVE_CDP_PORT", "9222"))
HOST = "127.0.0.1"
MATCH = os.environ.get("YT_PIP_MATCH", "youtube.com")

# Use YouTube's own player API, not video.playbackRate directly. Setting the
# element fights the player: it re-asserts its stored speed a moment later, so
# the change appears to take and then silently reverts. setPlaybackRate updates
# the player's own state, so it sticks (and the speed menu reflects it).
# Falls back to the raw element for any page without the YouTube player.
RATE_JS = """
(() => {
  const rate = %s;
  const p = document.getElementById('movie_player');
  if (p && typeof p.setPlaybackRate === 'function') {
    p.setPlaybackRate(rate);
    return String(typeof p.getPlaybackRate === 'function' ? p.getPlaybackRate() : rate);
  }
  const vids = [...document.querySelectorAll('video')].filter(v => v.readyState > 0);
  const v = vids.find(x => !x.paused) || vids[0];
  if (!v) return 'no-video';
  v.playbackRate = rate;
  return String(v.playbackRate);
})()
"""

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
    """
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"],
                             capture_output=True, text=True, timeout=3).stdout
        for c in json.loads(out or "[]"):
            if "brave-youtube" in (c.get("class") or ""):
                return (c.get("title") or "").strip()
    except Exception:
        pass
    return ""


def pick(ts):
    pages = [t for t in ts if t.get("type") == "page" and MATCH in t.get("url", "")]
    if not pages:
        return None
    # Prefer an actual watch page. YouTube can leave extra page targets around
    # (prerendered next videos, a homepage tab), and picking one of those sets
    # the rate on a video you are not watching -- which looks exactly like the
    # hotkey doing nothing.
    watch = [t for t in pages if "/watch" in t.get("url", "")]
    if len(watch) == 1:
        return watch[0]
    if watch:
        pages = watch
    if len(pages) == 1:
        return pages[0]

    want = webapp_title()
    if want:
        # CDP titles arrive HTML-escaped ("Q&amp;A"); the window title does not.
        for t in pages:
            title = html.unescape(t.get("title", "")).strip()
            if title and (title == want or title.startswith(want[:40])
                          or want.startswith(title[:40])):
                return t
    return pages[0]


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
    expr = TOGGLE_JS
    if len(sys.argv) > 2 and sys.argv[1] == "--rate":
        expr = RATE_JS % float(sys.argv[2])

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
    sys.exit(main())
