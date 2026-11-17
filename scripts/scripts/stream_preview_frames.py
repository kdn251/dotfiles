"""Paced hover-preview capture with one connection and one pending GTK frame."""
import threading
import time
from mpv_clip import Player


def pump_frames(preview, path, decode, submit, active, errors=(OSError, ValueError), fps=60):
    """submit(texture, done) must call done after displaying or discarding it."""
    player = None
    delivered = threading.Event()
    interval = 1 / fps
    try:
        while active() and not preview.cancelled.is_set():
            started = time.monotonic()
            try:
                if preview.process is None:
                    preview.cancelled.wait(.05)
                    continue
                if player is None:
                    player = Player(preview.endpoint, preview.process.pid)
                    player.socket.settimeout(.4)
                    player.command('set_property', 'screenshot-jpeg-quality', 65)
                player.command('screenshot-to-file', str(path), 'video')
                texture = decode(path)
                if not active() or preview.cancelled.is_set():
                    break
                delivered.clear()
                submit(texture, delivered.set)
                # Backpressure: never accumulate old frames in GTK's queue.
                while not delivered.wait(.02):
                    if not active() or preview.cancelled.is_set():
                        return
                # Capture/decode/display time counts toward the frame period.
                preview.cancelled.wait(max(0, started + interval - time.monotonic()))
            except errors:
                if player is not None:
                    player.close()
                    player = None
                preview.cancelled.wait(.05)
    finally:
        if player is not None:
            player.close()
        path.unlink(missing_ok=True)
