#!/usr/bin/env python3
"""Remember PiP geometry independently of focus and socket-event traffic."""
import json
import os
from pathlib import Path
import subprocess
import time


def clients():
    result = subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True,
                            text=True, check=True, timeout=2)
    return json.loads(result.stdout)


def geometry(client):
    return (*client['at'], *client['size'])


def is_pip(client):
    return client['class'] == 'mpv' or client['title'].lower().replace('-', ' ') == 'picture in picture'


def restore(address, saved):
    x, y, width, height = saved
    subprocess.run(['hyprctl', '--batch',
                    f'dispatch resizewindowpixel exact {width} {height},address:{address}; '
                    f'dispatch movewindowpixel exact {x} {y},address:{address}'],
                   stdout=subprocess.DEVNULL, check=True, timeout=2)


class Tracker:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.windows = {}

    def update(self, current):
        live = set()
        for client in current:
            if not client.get('mapped') or not client.get('floating') or not is_pip(client):
                continue
            address = client['address']
            key = (address, client['pid'])
            live.add(key)
            state = self.windows.setdefault(key, {'saved': None, 'fs': False})
            snapshot = self.runtime / f'pip-fullscreen-{os.getuid()}-{address}.geometry'
            # F / Mod+F captures exact geometry before entry, including moves
            # made between polling ticks. Atomic rename prevents partial reads.
            try:
                captured = json.loads(snapshot.read_text())
                if captured['pid'] == client['pid']:
                    state['saved'] = geometry(captured)
                    state['fs'] = True
                snapshot.unlink(missing_ok=True)
            except (OSError, ValueError, KeyError, TypeError):
                pass
            fullscreen = client['fullscreen'] != 0
            if not fullscreen and state['fs'] and state['saved'] is not None:
                # Restore once on exit. Repeated corrections fight intentional
                # dragging and corner shortcuts immediately after fullscreen.
                restore(address, state['saved'])
            elif not fullscreen:
                state['saved'] = geometry(client)
            state['fs'] = fullscreen
        self.windows = {key: value for key, value in self.windows.items() if key in live}


def main():
    tracker = Tracker(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    while True:
        try:
            tracker.update(clients())
        except (subprocess.SubprocessError, OSError, ValueError) as error:
            print(f'PiP position restore: {error}', flush=True)
        time.sleep(0.1)


if __name__ == '__main__':
    main()
