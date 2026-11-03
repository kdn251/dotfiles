#!/usr/bin/env python3
"""Toggle PiP fullscreen in one native compositor transaction."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HYPRCTL = '/usr/bin/hyprctl'


def query(kind):
    return json.loads(subprocess.check_output([HYPRCTL, kind, '-j']))


def lua(value):
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in value.items()) + '}'
    if isinstance(value, bool):
        return str(value).lower()
    return json.dumps(value)


def dispatch(method, **options):
    return 'hl.dispatch(hl.dsp.' + method + '(' + lua(options) + '))'


def is_pip(client):
    return client.get('class') == 'mpv' or re.fullmatch(
        'Picture[- ]in[- ]picture', client.get('title', ''), re.I)


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write(path, value):
    temp = Path(str(path) + '.tmp')
    temp.write_text(json.dumps(value) + '\n')
    temp.replace(path)


def toggle(client, runtime):
    address = client.get('address')
    if not address:
        return
    fullscreen = dispatch('window.fullscreen', mode='fullscreen', action='toggle')
    if not is_pip(client):
        subprocess.run([HYPRCTL, 'eval', fullscreen], check=True, stdout=subprocess.DEVNULL)
        return
    target = 'address:' + address
    prefix = runtime / f'pip-fullscreen-{os.getuid()}-{address}'
    geometry = Path(str(prefix) + '.geometry')
    snapshot = Path(str(geometry) + '.return')
    pin = Path(str(prefix) + '.pinned')
    pid = client['pid']
    commands = [dispatch('window.set_prop', window=target, prop='no_focus', value='0'),
                dispatch('focus', window=target)]
    restore = None
    if not client.get('fullscreen'):
        write(geometry, client)
        write(snapshot, client)
        pin.unlink(missing_ok=True)
        if client.get('pinned'):
            commands.append(dispatch('window.pin', window=target))
            write(pin, pid)
        commands.append(fullscreen)
    else:
        commands.append(fullscreen)
        saved = read(snapshot)
        if saved and saved.get('pid') == pid and saved.get('floating'):
            restore = saved
            commands.extend([
                dispatch('window.resize', window=target, x=saved['size'][0], y=saved['size'][1], relative=False),
                dispatch('window.move', window=target, x=saved['at'][0], y=saved['at'][1], relative=False)])
        if read(pin) == pid and not client.get('pinned'):
            commands.append(dispatch('window.pin', window=target))
    # Reset the temporary focus override even if an earlier dispatcher fails.
    reset = dispatch('window.set_prop', window=target, prop='no_focus', value='unset')
    script = 'local ok, err = pcall(function() ' + '; '.join(commands) + ' end); ' + reset + '; if not ok then error(err) end'
    subprocess.run([HYPRCTL, 'eval', script], check=True, stdout=subprocess.DEVNULL)
    if client.get('fullscreen'):
        if restore:
            write(Path(str(geometry) + '.restored'), pid)
            geometry.unlink(missing_ok=True)
            snapshot.unlink(missing_ok=True)
        pin.unlink(missing_ok=True)


def main():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
    with (runtime / f'pip-fullscreen-{os.getuid()}.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        clients = query('clients')
        if len(sys.argv) > 2 and sys.argv[1] == '--pid':
            pid = int(sys.argv[2])
            client = next((c for c in clients if c['pid'] == pid and c['class'] == 'mpv' and c['mapped']), {})
        else:
            pointer, workspace = query('cursorpos'), query('activeworkspace')
            candidates = [c for c in clients if c.get('mapped') and not c.get('hidden') and is_pip(c)
                          and (c.get('pinned') or c['workspace']['name'] == workspace['name'])
                          and c['at'][0] <= pointer['x'] < c['at'][0] + c['size'][0]
                          and c['at'][1] <= pointer['y'] < c['at'][1] + c['size'][1]]
            candidates.sort(key=lambda c: c['focusHistoryID'] if c['focusHistoryID'] >= 0 else 999999)
            client = candidates[0] if candidates else query('activewindow')
        toggle(client, runtime)


if __name__ == '__main__':
    main()
