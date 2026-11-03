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

    def update(self, current, layout=None):
        live = set()
        for client in current:
            if not client.get('mapped') or not client.get('floating') or not is_pip(client):
                continue
            address = client['address']
            key = (address, client['pid'])
            live.add(key)
            state = self.windows.setdefault(key, {'saved': None, 'fs': False})
            snapshot = self.runtime / f'pip-fullscreen-{os.getuid()}-{address}.geometry'
            restored = snapshot.with_name(snapshot.name + '.restored')
            try:
                if int(restored.read_text()) == client['pid'] and not client['fullscreen']:
                    state['saved'] = geometry(client)
                    state['fs'] = False
                    snapshot.unlink(missing_ok=True)
                restored.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
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
            if layout and not fullscreen and not state['fs']:
                from pip_geometry import bounds, align_default, bottom_right
                monitors,gaps,border=layout
                monitor=next((m for m in monitors if m['id']==client['monitor']),None)
                if monitor:
                    edges=bounds(monitor,gaps,border)
                    previous=state.get('edges')
                    saved=state['saved']
                    at=client['at']
                    if previous is None:
                        at=align_default(client,monitor,gaps,border)
                    elif previous!=edges and saved and abs(saved[0]+saved[2]-previous[2])<=2 and abs(saved[1]+saved[3]-previous[3])<=2:
                        at=bottom_right(monitor,client['size'],gaps,border)
                    if at!=client['at']:
                        restore(address,(*at,*client['size']))
                        client=dict(client,at=at)
                    state['edges']=edges
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
    layout=None;refresh_at=0
    while True:
        try:
            if time.monotonic()>=refresh_at:
                from pip_geometry import settings
                monitors=json.loads(subprocess.check_output(['hyprctl','-j','monitors'],text=True,timeout=2))
                layout=(monitors,*settings());refresh_at=time.monotonic()+2
            tracker.update(clients(),layout)
        except (subprocess.SubprocessError, OSError, ValueError) as error:
            print(f'PiP position restore: {error}', flush=True)
        time.sleep(0.1)


if __name__ == '__main__':
    main()
