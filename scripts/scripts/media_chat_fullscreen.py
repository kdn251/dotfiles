"""Reserve part of a fullscreen MPV canvas for a live-chat window."""
import fcntl
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time

ROOT = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
STATE = ROOT / f'media-chat-fullscreen-{os.getuid()}.json'
OWNER = ROOT / 'media-chat-workspace-owner'
PREFERENCE = ROOT / f'media-chat-fullscreen-return-{os.getuid()}.json'
WORKSPACE = 'chatterino_chat'
CLASSES = {'com.chatterino.chatterino', 'newsboat-live-chat'}
PROPERTIES = {'keepaspect': True, 'panscan': 0, 'video-zoom': 0,
              'video-pan-x': 0, 'video-pan-y': 0, 'video-scale-x': 1,
              'video-scale-y': 1, 'video-align-x': 0, 'video-align-y': 0,
              'video-margin-ratio-left': 0, 'video-margin-ratio-right': 0,
              'video-margin-ratio-top': 0, 'video-margin-ratio-bottom': 0}


def hypr(*args):
    return subprocess.check_output(['hyprctl', *args], text=True, timeout=2)


def ipc(state, *command):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(2)
        client.connect(state['socket'])
        pid, uid, _ = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if pid != state['player']['pid'] or uid != os.getuid():
            raise ValueError('Player changed')
        client.sendall((json.dumps({'command': command, 'request_id': 9}) + '\n').encode())
        with client.makefile('rb') as stream:
            for line in stream:
                reply = json.loads(line)
                if reply.get('request_id') == 9:
                    if reply.get('error') != 'success':
                        raise ValueError('Player rejected layout property')
                    return reply.get('data')
        raise ValueError('Player disconnected')


def socket_for(player):
    args = Path(f"/proc/{player['pid']}/cmdline").read_bytes().split(b'\0')
    paths = ['/tmp/mpv-twitch-ipc'] + [f'/tmp/mpv-{s}-live-ipc' for s in ('youtube', 'rumble', 'kick')]
    return next((path for path in paths if ('--input-ipc-server=' + path).encode() in args), None)


def regular_workspace(player, state=None):
    """A replacement MPV can inherit the focused chat's special workspace."""
    if player.get('workspace', {}).get('id', 0) > 0:
        return player
    monitors = json.loads(hypr('-j', 'monitors'))
    monitor = next((m for m in monitors if m['id'] == player.get('monitor')), None)
    if not monitor:
        return player
    desired = (state or {}).get('player', {}).get('workspace', {}).get('id', 0)
    if desired <= 0:
        desired = monitor.get('activeWorkspace', {}).get('id', 0)
    if desired <= 0:
        return player
    hypr('dispatch', 'movetoworkspacesilent', f"{desired},address:{player['address']}")
    return next((c for c in json.loads(hypr('-j', 'clients'))
                 if c['address'] == player['address'] and c['pid'] == player['pid']), player)


def place_player(pid):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            clients = json.loads(hypr('-j', 'clients'))
            player = next((c for c in clients if c.get('pid') == pid and c.get('class') == 'mpv'), None)
            if player:
                regular_workspace(player, read())
                return
            os.kill(pid, 0)
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        time.sleep(.05)


def layout(monitor, youtube=False, video=None):
    width, height = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2:
        width, height = height, width
    width = round(width / monitor.get('scale', 1))
    height = round(height / monitor.get('scale', 1))
    chat_width = min(round(width * .4), max(320 if youtube else 240, min(520, round(width * (.30 if youtube else .20)))))
    return {'at': [monitor['x'] + width - chat_width, monitor['y']],
            'size': [chat_width, height], 'ratio': chat_width / width}



def style(chat, inline):
    address = chat['address']
    values = {'no_shadow': '1', 'border_size': '0', 'rounding': '0'}
    hypr('--batch', '; '.join(f'dispatch setprop address:{address} {prop} {value if inline else "unset"}'
                             for prop, value in values.items()))


def move(chat, bounds):
    address = chat['address']
    w, h = bounds['size']; x, y = bounds['at']
    hypr('--batch', f'dispatch resizewindowpixel exact {w} {h},address:{address}; '
         f'dispatch movewindowpixel exact {x} {y},address:{address}')


def read():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def toggle_on_monitor(monitor, monitors):
    focused = next((m for m in monitors if m.get('focused')), None)
    if focused and focused['id'] != monitor['id']:
        hypr('dispatch', 'focusmonitor', str(monitor['id']))
    hypr('dispatch', 'togglespecialworkspace', WORKSPACE)
    if focused and focused['id'] != monitor['id']:
        hypr('dispatch', 'focusmonitor', str(focused['id']))


def hide_workspace(monitors):
    visible = next((m for m in monitors if m.get('specialWorkspace', {}).get('name') == 'special:' + WORKSPACE), None)
    if visible:
        toggle_on_monitor(visible, monitors)


def restore(state, clients, hide=True):
    OWNER.unlink(missing_ok=True)
    if 'special_fallthrough' in state:
        hypr('keyword', 'input:special_fallthrough', str(state['special_fallthrough']))
    for prop, value in state.get('properties', {}).items():
        try:
            ipc(state, 'set_property', prop, value)
        except (OSError, ValueError):
            break
    old = state['chat']
    chat = next((c for c in clients if c['address'] == old['address'] and c['pid'] == old['pid']), None)
    if hide:
        hide_workspace(json.loads(hypr('-j', 'monitors')))
    if chat:
        style(chat, False)
        move(chat, old)
    STATE.unlink(missing_ok=True)


def focus_player():
    """After revealing theater chat, return keyboard focus to its video once."""
    state = read()
    if not state:
        return
    clients = json.loads(hypr('-j', 'clients'))
    player = next((c for c in clients if c.get('pid') == state['player']['pid'] and
                   c.get('address') == state['player']['address'] and c.get('fullscreen') == 2), None)
    if not player:
        return
    monitors = json.loads(hypr('-j', 'monitors'))
    monitor = next((m for m in monitors if m['id'] == player['monitor']), None)
    if monitor and monitor.get('activeWorkspace', {}).get('id') == player.get('workspace', {}).get('id'):
        hypr('dispatch', 'focuswindow', 'address:' + player['address'])


def remember_theater(player):
    PREFERENCE.write_text(json.dumps({'pid': player['pid'], 'address': player['address']}))
    PREFERENCE.chmod(0o600)


def resume_theater(clients):
    try:
        saved = json.loads(PREFERENCE.read_text())
    except (OSError, ValueError):
        return False
    player = next((c for c in clients if c.get('pid') == saved.get('pid') and
                   c.get('address') == saved.get('address')), None)
    if not player:
        PREFERENCE.unlink(missing_ok=True)
        return False
    if player.get('fullscreen') != 2:
        return False
    # Only reopen on the player's visible workspace; don't pull chat across
    # another workspace or duplicate an opener that is still launching.
    monitor = next((m for m in json.loads(hypr('-j', 'monitors')) if m['id'] == player['monitor']), None)
    if not monitor or monitor.get('activeWorkspace', {}).get('id') != player.get('workspace', {}).get('id'):
        return True
    if time.monotonic() - saved.get('attempt', 0) < 10:
        return True
    saved['attempt'] = time.monotonic()
    PREFERENCE.write_text(json.dumps(saved))
    subprocess.Popen(['python3', str(Path(__file__).with_name('media-chat.py')), '--handoff'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return True


def close(clients):
    with STATE.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read()
        if not state:
            return False
        # Mod+C explicitly selects ordinary fullscreen for the next return.
        PREFERENCE.unlink(missing_ok=True)
        restore(state, clients)
        return True


def player_service(player, endpoint):
    from stream_player_identity import identity
    current = identity(player)
    if current:
        return current[0]
    return next((s for s in ('YouTube', 'Kick', 'Rumble') if s.lower() in endpoint), 'Twitch')


def adopt_chat(state, clients):
    """Replace only the chat pane; keep the fullscreen canvas and reservation."""
    player = next((c for c in clients if c.get('pid') == state['player']['pid']), None)
    if not player:
        return False
    service = player_service(player, state['socket'])
    klass = 'com.chatterino.chatterino' if service == 'Twitch' else 'newsboat-live-chat'
    chat = next((c for c in clients if c.get('class') == klass and
                 c.get('workspace', {}).get('name') != 'special:media_chat_closing'), None)
    if not chat:
        return False
    monitors = json.loads(hypr('-j', 'monitors'))
    monitor = next(m for m in monitors if m['id'] == player['monitor'])
    bounds = layout(monitor, service == 'YouTube')
    state.update(player=player, chat=chat, service=service, created=time.monotonic())
    state.pop('transition', None)
    style(chat, True)
    move(chat, bounds)
    ipc(state, 'set_property', 'video-margin-ratio-right', bounds['ratio'])
    STATE.write_text(json.dumps(state))
    owner_tmp = OWNER.with_suffix('.tmp')
    owner_tmp.write_text(f"{player['workspace']['id']} {player['monitor']} {chat.get('workspace', {}).get('id', 0)}\n")
    owner_tmp.replace(OWNER)
    return True


def begin(clients=None):
    with STATE.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = read()
        if existing:
            if existing.get("transition"):
                adopt_chat(existing, clients if clients is not None else json.loads(hypr("-j", "clients")))
            return True
        if clients is None:
            clients = json.loads(hypr('-j', 'clients'))
        players = [c for c in clients if c.get('class') == 'mpv' and c.get('fullscreen') == 2]
        players.sort(key=lambda c: c.get('focusHistoryID', 999))
        for player in players:
            player = regular_workspace(player)
            endpoint = socket_for(player)
            if not endpoint:
                continue
            service = player_service(player, endpoint)
            chat_class = 'com.chatterino.chatterino' if service == 'Twitch' else 'newsboat-live-chat'
            chat = next((c for c in clients if c.get('class') == chat_class), None)
            if not chat:
                continue
            monitors = json.loads(hypr('-j', 'monitors'))
            monitor = next(m for m in monitors if m['id'] == player['monitor'])
            if monitor.get('activeWorkspace', {}).get('id') != player.get('workspace', {}).get('id'):
                continue
            bounds = layout(monitor, service == 'YouTube')
            state = {'player': player, 'chat': chat, 'socket': endpoint, 'service': service,
                     'properties': {}, 'created': time.monotonic(),
                     'special_fallthrough': json.loads(hypr('-j', 'getoption', 'input:special_fallthrough')).get('int', 0)}
            for prop in PROPERTIES:
                state['properties'][prop] = ipc(state, 'get_property', prop)
            STATE.write_text(json.dumps(state)); STATE.chmod(0o600)
            PREFERENCE.unlink(missing_ok=True)
            owner_tmp = OWNER.with_suffix('.tmp')
            owner_tmp.write_text(f"{player['workspace']['id']} {player['monitor']} {chat.get('workspace', {}).get('id', 0)}\n")
            owner_tmp.replace(OWNER)
            try:
                hypr('keyword', 'input:special_fallthrough', '1')
                for prop, value in dict(PROPERTIES, **{'video-margin-ratio-right': bounds['ratio']}).items():
                    ipc(state, 'set_property', prop, value)
                style(chat, True)
                move(chat, bounds)
                hypr('dispatch', 'focusmonitor', str(player['monitor']))
            except Exception:
                restore(state, clients, hide=False)
                raise
            return True
    return False


def maintain(clients):
    """Undo the reservation on fullscreen exit, closed chat, or closed player."""
    with STATE.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        state = read()
        if not state:
            return resume_theater(clients)
        transition = state.get('transition')
        if transition and time.monotonic() < transition['deadline']:
            # The launcher is replacing the player/chat. Keep the preference
            # while their windows are temporarily absent.
            return True
        player = next((c for c in clients if c['address'] == state['player']['address'] and c['pid'] == state['player']['pid']), None)
        chat = next((c for c in clients if c['address'] == state['chat']['address'] and c['pid'] == state['chat']['pid']), None)
        if not player or not chat or player.get('fullscreen') != 2:
            if player and chat and player.get('fullscreen') != 2:
                remember_theater(player)
            else:
                PREFERENCE.unlink(missing_ok=True)
            restore(state, clients, hide=True)
            return False
        monitors = json.loads(hypr('-j', 'monitors'))
        monitor = next((m for m in monitors if m['id'] == player['monitor']), None)
        # Special workspaces otherwise remain visible over unrelated normal
        # workspaces. Scope this layout to the workspace containing the stream.
        if monitor and monitor.get('activeWorkspace', {}).get('id') != player.get('workspace', {}).get('id'):
            hide_workspace(monitors)
            if not state.get('suspended'):
                state['suspended'] = True
                STATE.write_text(json.dumps(state))
            return True
        if monitor and state.get('suspended'):
            if monitor.get('specialWorkspace', {}).get('name') != 'special:' + WORKSPACE:
                toggle_on_monitor(monitor, monitors)
                monitor['specialWorkspace'] = {'name': 'special:' + WORKSPACE}
            state['suspended'] = False
            STATE.write_text(json.dumps(state))
            focus_player()
        if not monitor or monitor.get('specialWorkspace', {}).get('name') != 'special:' + WORKSPACE:
            if time.monotonic() - state.get('created', 0) < 1:
                return True
            restore(state, clients, hide=False)
            return False
        bounds = layout(monitor, state.get('service') == 'YouTube' or state['socket'].endswith('mpv-youtube-live-ipc'))
        if chat['at'] != bounds['at'] or chat['size'] != bounds['size']:
            move(chat, bounds)
            ipc(state, 'set_property', 'video-margin-ratio-right', bounds['ratio'])
        return True


def prepare_transition(session, service, name):
    with STATE.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read()
        if not state:
            return
        # New chats inherit the normal floating window rules. Stage them in
        # the hidden special workspace until adopt_chat has applied the full
        # height geometry. Disable automatic workspace re-show during staging.
        OWNER.unlink(missing_ok=True)
        hide_workspace(json.loads(hypr('-j', 'monitors')))
        state['transition'] = {'session': session, 'service': service,
                               'name': name, 'deadline': time.monotonic() + 60}
        STATE.write_text(json.dumps(state))
    subprocess.Popen(['python3', __file__, 'resume', session], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def replacement(state, clients):
    transition = state['transition']
    service = transition['service']
    endpoint = '/tmp/mpv-twitch-ipc' if service == 'Twitch' else f'/tmp/mpv-{service.lower()}-live-ipc'
    for player in clients:
        if player.get('class') != 'mpv' or not player.get('mapped', True):
            continue
        try:
            from stream_player_identity import identity
            current = identity(player)
            actual = socket_for(player)
            if current:
                if current[0] != service or current[1].lower() != transition['name'].lower():
                    continue
            elif actual != endpoint or (service != 'Twitch' and player['pid'] == state['player']['pid']):
                continue
            candidate = {'player': player, 'socket': actual}
            if service == 'Twitch':
                if ipc(candidate, 'get_property', 'user-data/twitch-channel').lower() != transition['name'].lower():
                    continue
                marker = ROOT / f'twitch-chat-channel-{os.getuid()}'
                if marker.read_text().strip() != transition['name'].lower():
                    continue
                if not any(c.get('class') == 'com.chatterino.chatterino' for c in clients):
                    continue
            if ipc(candidate, 'get_property', 'time-pos') is None:
                continue
            return player
        except (OSError, ValueError, AttributeError):
            continue
    return None


def resume_transition(session):
    while True:
        try:
            if Path('/tmp/twitch-session.id').read_text().strip() != session:
                return
            state = read()
            if not state or state.get('transition', {}).get('session') != session:
                return  # Explicit Mod+C cancellation or a newer selection.
            if time.monotonic() >= state['transition']['deadline']:
                return
            clients = json.loads(hypr('-j', 'clients'))
            player = replacement(state, clients)
            if player:
                player = regular_workspace(player, state)
                if player['pid'] == state['player']['pid']:
                    subprocess.run(['python3', str(Path(__file__).with_name('media-chat.py')), '--handoff'], timeout=20)
                    return
                with STATE.with_suffix('.lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    current = read()
                    if not current or current.get('transition', {}).get('session') != session:
                        return
                    restore(current, clients)
                if not player.get('fullscreen'):
                    subprocess.run([str(Path(__file__).with_name('toggle-pip-fullscreen.sh')),
                                    '--pid', str(player['pid'])], check=True, timeout=5)
                # The ordinary opener supplies the matching platform's chat and
                # reapplies the fullscreen layout once its window is ready.
                subprocess.run(['python3', str(Path(__file__).with_name('media-chat.py'))], timeout=20)
                return
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        time.sleep(.1)


if __name__ == '__main__':
    import sys
    if sys.argv[1] == 'prepare':
        prepare_transition(*sys.argv[2:])
    elif sys.argv[1] == 'place':
        place_player(int(sys.argv[2]))
    elif sys.argv[1] == 'resume':
        resume_transition(sys.argv[2])
