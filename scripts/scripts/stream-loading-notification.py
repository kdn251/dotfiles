#!/usr/bin/env python3
"""Dismiss only this launch's loading notice when its stream starts playing."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location('stream_ipc', Path(__file__).with_name('twitch-player-ipc.py'))
ipc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipc)


def watch(session, notification):
    if not notification.isdigit(): return
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        try:
            if Path('/tmp/twitch-session.id').read_text().strip() != session:
                break
            client, _ = ipc.connect()
            with client, client.makefile('rwb', buffering=0) as stream:
                ready = ipc.command(stream, 'get_property', 'user-data/stream-ready-session')
            if ready == session: break
        except (OSError, ValueError): pass
        time.sleep(.05)
    subprocess.run(['makoctl', 'dismiss', '-n', notification], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    watch(*sys.argv[1:])
