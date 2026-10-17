#!/usr/bin/env python3
"""Toggle between a visible video and the exact window that invoked it."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def query(command):
    return json.loads(subprocess.check_output(['hyprctl', '-j', command], text=True, timeout=2))


def media(window):
    return (window.get('class') == 'mpv' or
            bool(re.fullmatch(r'Picture[- ]in[- ]picture', window.get('title', ''), re.I)) or
            (window.get('class') == 'vesktop' and window.get('floating')))


def recent(window):
    rank = window.get('focusHistoryID', -1)
    return rank if rank >= 0 else float('inf')


def choose(clients, active, workspace, saved):
    visible = [w for w in clients if w.get('mapped') and not w.get('hidden')
               and not w['workspace']['name'].startswith('special:')
               and (w.get('pinned') or w['workspace']['id'] == workspace)]
    if media(active):
        others = [w for w in visible if not media(w)]
        # Check PID too, in case a closed window's address has been reused.
        target = next((w for w in others if
                       [w['address'], w.get('pid')] == saved.get('return')), None)
        return target or min(others, key=recent, default=None), saved
    videos = [w for w in visible if media(w)]
    target = min(videos, key=recent, default=None)
    if target and active.get('address'):
        saved = {'return': [active['address'], active.get('pid')]}
    return target, saved


def main():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    session = re.sub(r'[^a-zA-Z0-9_-]', '_', os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', 'default'))
    statefile = runtime / f'pip-focus-{session}.json'
    with (runtime / f'pip-focus-{session}.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        clients, active, workspace = query('clients'), query('activewindow'), query('activeworkspace')['id']
        try:
            states = json.loads(statefile.read_text())
        except (OSError, ValueError):
            states = {}
        key = str(workspace)
        target, saved = choose(clients, active, workspace, states.get(key, {}))
        if target:
            address = 'address:' + target['address']
            if media(target):
                # Pinned MPV and browser PiP have no_focus rules. Override
                # only for this deliberate keyboard focus, then restore rules.
                try:
                    subprocess.run(['hyprctl', '--batch',
                                    f'dispatch setprop {address} no_focus 0; '
                                    f'dispatch focuswindow {address}'], check=True, timeout=2)
                finally:
                    subprocess.run(['hyprctl', 'dispatch', 'setprop',
                                    address + ' no_focus unset'], check=True, timeout=2)
            else:
                subprocess.run(['hyprctl', 'dispatch', 'focuswindow', address], check=True, timeout=2)
            states[key] = saved
            statefile.write_text(json.dumps(states))
        elif not media(active):
            subprocess.run(['hyprctl', 'dispatch', 'cyclenext',
                            'prev' if sys.argv[1:] == ['prev'] else ''], check=True, timeout=2)


if __name__ == '__main__':
    main()
