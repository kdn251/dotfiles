#!/usr/bin/env python3
"""Toggle PiP fullscreen in one native compositor transaction."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

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


def managed_stream_toggle(client,runtime,force_exit=False):
    if client.get('class')!='mpv':return False
    from media_chat_fullscreen import socket_for,ipc
    try:
        endpoint=socket_for(client)
        if not endpoint:return False
        state={'player':client,'socket':endpoint}
        if ipc(state,'get_property','user-data/stream-service') not in ('Twitch','Kick','YouTube','Rumble'):return False
    except (OSError,ValueError):return False
    prefix=runtime/f"pip-fullscreen-{os.getuid()}-{client['address']}"
    geometry=Path(str(prefix)+'.geometry');snapshot=Path(str(geometry)+'.return')
    target='address:'+client['address']
    fullscreen=force_exit or bool(client.get('fullscreen') or ipc(state,'get_property','fullscreen'))
    if not fullscreen:
        write(geometry,client);write(snapshot,client)
        if client.get('pinned'):
            subprocess.run([HYPRCTL,'eval',dispatch('window.pin',window=target)],check=True,stdout=subprocess.DEVNULL)
        ipc(state,'set_property','fullscreen',True)
    else:
        from media_chat_fullscreen import leave_fullscreen
        try:leave_fullscreen(client['pid'])
        except (OSError,ValueError,subprocess.SubprocessError):pass
        ipc(state,'set_property','fullscreen',False)
        # Wait only for the compositor acknowledgment, not a fixed sleep.
        deadline=time.monotonic()+.25
        while time.monotonic()<deadline:
            current=next((c for c in query('clients') if c.get('pid')==client['pid']),None)
            if not current or not current.get('fullscreen'):break
            time.sleep(.005)
        from stream_sidebar import restore_windowed
        restore_windowed(client)
        write(Path(str(geometry)+'.restored'),client['pid'])
        geometry.unlink(missing_ok=True);snapshot.unlink(missing_ok=True)
    return True


def toggle(client, runtime,force_exit=False):
    if managed_stream_toggle(client,runtime,force_exit):return
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
        toggle(client, runtime,force_exit='--exit' in sys.argv)


if __name__ == '__main__':
    main()
