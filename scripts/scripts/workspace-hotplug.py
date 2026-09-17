#!/usr/bin/env python3
"""Remember the last stable workspace and restore it after Kanshi hotplug."""
import fcntl
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import time

RUNTIME = Path(os.environ['XDG_RUNTIME_DIR']) / 'hypr' / os.environ['HYPRLAND_INSTANCE_SIGNATURE']
STATE = RUNTIME / 'last-user-workspace'
LOCK = RUNTIME / 'workspace-hotplug.lock'


def query(name):
    return json.loads(subprocess.check_output(['hyprctl', name, '-j']))


def valid(value):
    return isinstance(value, int) and 1 <= value <= 7


def remember(value):
    if valid(value):
        temp = STATE.with_suffix('.tmp')
        temp.write_text(str(value))
        temp.replace(STATE)


def saved():
    try:
        value = int(STATE.read_text())
        if valid(value):
            return value
    except (OSError, ValueError):
        pass
    value = query('activeworkspace').get('id')
    return value if valid(value) else 1


def watch():
    with (RUNTIME / 'workspace-watch.lock').open('w') as singleton:
        try:
            fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        with socket.socket(socket.AF_UNIX) as sock, LOCK.open('a') as lock:
            sock.connect(str(RUNTIME / '.socket2.sock'))
            remember(query('activeworkspace').get('id'))
            pending = None
            deadline = 0.0
            frozen_until = 0.0
            buffer = ''
            while True:
                ready, _, _ = select.select([sock], [], [], 0.1)
                if ready:
                    chunk = sock.recv(65536)
                    if not chunk:
                        return
                    buffer += chunk.decode(errors='replace')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        event, _, payload = line.partition('>>')
                        if event.startswith(('monitoradded', 'monitorremoved')):
                            pending = None
                            frozen_until = time.monotonic() + 3
                        elif event == 'workspacev2':
                            try:
                                value = int(payload.split(',', 1)[0])
                            except ValueError:
                                continue
                            if valid(value) and time.monotonic() >= frozen_until:
                                pending = value
                                # Discard focus changes immediately preceding a hotplug event.
                                deadline = time.monotonic() + 0.3
                if pending is not None and time.monotonic() >= deadline:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pending = None
                        continue
                    try:
                        if query('activeworkspace').get('id') == pending:
                            remember(pending)
                    finally:
                        fcntl.flock(lock, fcntl.LOCK_UN)
                    pending = None


def apply(mode):
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        workspace = saved()
        # Wait until Kanshi has finished enabling one display and disabling the other.
        target = None
        stable_since = time.monotonic()
        for _ in range(50):
            monitors = query('monitors')
            candidate = None
            if len(monitors) == 1:
                name = monitors[0]['name']
                if name.startswith('eDP') == (mode == 'undocked'):
                    candidate = name
            if candidate != target or candidate is None:
                target = candidate
                stable_since = time.monotonic()
            if target and time.monotonic() - stable_since >= 1:
                break
            time.sleep(0.2)
        else:
            # A superseded hook must not move workspaces to the wrong output.
            return
        for item in query('workspaces'):
            if valid(item['id']) and item['monitor'] != target:
                subprocess.run(['hyprctl', 'dispatch', 'moveworkspacetomonitor',
                                f"{item['id']} {target}"], check=True)
        subprocess.run(['hyprctl', 'dispatch', 'workspace', str(workspace)], check=True)
        remember(workspace)
        # Leaving an empty transient hotplug workspace lets Hyprland remove it.
        subprocess.run(['systemctl', '--user', 'restart', 'waybar.service'], check=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--watch']:
        watch()
    elif len(sys.argv) == 3 and sys.argv[1] == '--apply' and sys.argv[2] in ('docked', 'undocked'):
        apply(sys.argv[2])
    else:
        sys.exit('Usage: workspace-hotplug.py --watch | --apply docked|undocked')
