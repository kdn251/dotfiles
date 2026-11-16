#!/usr/bin/env python3
"""Toggle between a visible video and the exact window that invoked it."""
import fcntl
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys


def request(command):
    # hyprctl's response polling adds ~50 ms to every call. Read the same
    # compositor IPC socket directly so a focus toggle needs no polling sleeps
    # or child processes.
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    endpoint = runtime / 'hypr' / os.environ['HYPRLAND_INSTANCE_SIGNATURE'] / '.socket.sock'
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(endpoint))
        connection.sendall(command.encode())
        chunks = []
        while chunk := connection.recv(65536):
            chunks.append(chunk)
    return b''.join(chunks).decode()


def query(command):
    return json.loads(request('j/' + command))


def dispatch(command):
    # Hyprland 0.57 uses Lua dispatchers; hyprctl translates legacy names.
    name, _, arguments = command.partition(' ')
    if name == 'focuswindow':
        expression = 'hl.dsp.focus({window=' + json.dumps(arguments) + '})'
    elif name == 'setprop':
        window, prop, value = arguments.split()
        expression = 'hl.dsp.window.set_prop({' + ','.join(
            key + '=' + json.dumps(value) for key, value in
            [('window', window), ('prop', prop), ('value', value)]) + '})'
    else:
        # Retain hyprctl's compatibility translation for ordinary cycling.
        subprocess.run(['hyprctl', 'dispatch', name, arguments], check=True, timeout=2)
        return
    response = request('/eval hl.dispatch(' + expression + ')').strip()
    if response != 'ok':
        raise RuntimeError(f'Hyprland {command}: {response}')


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
                # Some browser PiP windows have no_focus rules. Override
                # only for this deliberate keyboard focus, then restore rules.
                try:
                    dispatch(f'setprop {address} no_focus 0')
                    dispatch(f'focuswindow {address}')
                finally:
                    dispatch(f'setprop {address} no_focus unset')
            else:
                dispatch(f'focuswindow {address}')
            states[key] = saved
            statefile.write_text(json.dumps(states))
        elif not media(active):
            dispatch('cyclenext ' + ('prev' if sys.argv[1:] == ['prev'] else ''))


if __name__ == '__main__':
    main()
