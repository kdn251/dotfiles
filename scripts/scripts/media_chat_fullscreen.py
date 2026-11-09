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
    endpoint = next((path for path in paths if ('--input-ipc-server=' + path).encode() in args), None)
    if endpoint:return endpoint
    # Promoted previews retain their private socket; the canonical one aliases it.
    prefix = str(ROOT / 'stream-preview') + '/'
    return next((arg.decode().split('=',1)[1] for arg in args
                 if arg.startswith(('--input-ipc-server='+prefix).encode())), None)


def regular_workspace(player, state=None):
    """A replacement MPV can inherit the focused chat's special workspace."""
    if player.get('workspace', {}).get('id', 0) > 0:
        return player
    monitors = json.loads(hypr('-j', 'monitors'))
    hidden = player.get('workspace', {}).get('name') == 'special:mpvhidden'
    monitor = next((m for m in monitors if (m.get('focused') if hidden else m['id'] == player.get('monitor'))), None)
    if not monitor:
        return player
    desired = 0 if hidden else (state or {}).get('player', {}).get('workspace', {}).get('id', 0)
    if desired <= 0:
        desired = monitor.get('activeWorkspace', {}).get('id', 0)
    if desired <= 0:
        return player
    hypr('dispatch', 'movetoworkspacesilent', f"{desired},address:{player['address']}")
    return next((c for c in json.loads(hypr('-j', 'clients'))
                 if c['address'] == player['address'] and c['pid'] == player['pid']), player)


def reveal_player(pid):
    """A new stream selection restores only its own Mod+H-hidden window."""
    try:
        player = next((c for c in json.loads(hypr('-j','clients')) if c.get('pid')==pid and c.get('class')=='mpv'),None)
        if not player or player.get('workspace',{}).get('name')!='special:mpvhidden':return
        address=player['address']
        if player.get('pinned'):hypr('dispatch','pin','address:'+address)
        player=regular_workspace(player)
        saved=ROOT/'pip-hidden-pinned'
        lines=saved.read_text().splitlines() if saved.exists() else []
        if address in lines and not player.get('pinned'):
            hypr('dispatch','pin','address:'+address)
        if address in lines:
            saved.write_text(''.join(line+'\n' for line in lines if line!=address))
    except (OSError,ValueError,subprocess.SubprocessError):pass


def place_player(pid, align=True):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            clients = json.loads(hypr('-j', 'clients'))
            player = next((c for c in clients if c.get('pid') == pid and c.get('class') == 'mpv'), None)
            if player:
                player = regular_workspace(player, read())
                if align and not player.get('fullscreen'):
                    from pip_geometry import settings, align_default
                    monitor = next((m for m in json.loads(hypr('-j','monitors')) if m['id']==player['monitor']),None)
                    if monitor:
                        at = align_default(player,monitor,*settings())
                        if at != player['at']:
                            hypr('dispatch','movewindowpixel',f"exact {at[0]} {at[1]},address:{player['address']}")
                # Pin on explicit opens; later manual unpinning stays respected.
                # Fullscreen/theater uses its existing workspace handling.
                if not player.get('fullscreen') and not player.get('pinned'):
                    if not player.get('floating'):
                        hypr('dispatch', 'setfloating', 'address:' + player['address'])
                    hypr('dispatch', 'pin', 'address:' + player['address'])
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
    chat_width = min(round(width * .4), max(240, min(520, round(width * .20))))
    return {'at': [monitor['x'] + width - chat_width, monitor['y']],
            'size': [chat_width, height], 'ratio': chat_width / width}



def panel_space(state, ratio, animate=False):
    from media_panel_layout import update
    native_slide=(ROOT/'media-chat-slide-enabled').exists()
    if native_slide:(ROOT/'media-chat-slide-socket').write_text(state['socket']+'\n')
    def command(*args):
        # Keep the current visible margin until the compositor starts sliding.
        # Its animation progress then owns this one property, frame by frame.
        if native_slide and animate and args[:2]==('set_property','video-margin-ratio-right'):return
        return ipc(state,*args)
    update(command,state['player']['pid'],'right',ratio,
           fallback=state.get('properties'))


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


def prepare_chat_window():
    """New chat windows must map out of view until begin() sizes the pane."""
    clients=json.loads(hypr('-j','clients'))
    if any(c.get('class')=='mpv' and c.get('fullscreen')==2 for c in clients):
        hide_workspace(json.loads(hypr('-j','monitors')))


def retire_chat_window(address):
    """Remove chat from focus before its asynchronous process shutdown."""
    target=json.dumps('address:'+address)
    script=('local previous=hl.get_config("misc.on_focus_under_fullscreen"); '
            'hl.config({misc={on_focus_under_fullscreen=0}}); '
            'local ok,err=pcall(function() '
            'hl.dispatch(hl.dsp.window.move({workspace="special:media_chat_closing",follow=false,window='+target+'})); '
            'hl.dispatch(hl.dsp.window.close({window='+target+'})) end); '
            'hl.config({misc={on_focus_under_fullscreen=previous}}); '
            'if not ok then error(err) end')
    hypr('eval',script)


def chat_slide_style(clients, monitors):
    players = sorted((c for c in clients if c.get('class') == 'mpv'),
                     key=lambda c:c.get('focusHistoryID',999))
    if not players:return 'slide 20%'
    player=players[0]
    monitor=next((m for m in monitors if m['id']==player['monitor']),None)
    if not monitor:return 'slide 20%'
    visible=monitor.get('specialWorkspace',{}).get('name')=='special:'+WORKSPACE
    chat=next((c for c in clients if c.get('class') in CLASSES and
               c.get('workspace',{}).get('name')=='special:'+WORKSPACE),None)
    # Theater comes from the screen's right edge. Floating chat comes from
    # the adjacent player: a pane on its right moves left-to-right on entry.
    from_right=bool(player.get('fullscreen')) or not chat or chat['at'][0]<player['at'][0]
    direction=('left' if from_right else 'right') if visible else ('right' if from_right else 'left')
    width=monitor['height'] if monitor.get('transform',0)%2 else monitor['width']
    width/=monitor.get('scale',1)
    percent=max(1,round(100*chat['size'][0]/width)) if chat else 20
    return f'slide {direction} {percent}%'


def toggle_workspace(animate=True):
    """Map/unmap chat without Hyprland exiting the video's fullscreen mode."""
    # The normal policy (2) exits fullscreen when special-workspace focus moves
    # underneath it. Override only inside this compositor transaction, then
    # restore the user's policy before another event or frame can run.
    try:
        animation=chat_slide_style(json.loads(hypr('-j','clients')),json.loads(hypr('-j','monitors')))
    except (OSError,ValueError,KeyError,TypeError):
        animation='slide 20%'
    # Apply the rule before toggling so the compositor refreshes the workspace
    # style first, including when changing between floating and theater chat.
    hypr('eval','hl.workspace_rule({workspace="special:chatterino_chat",animation='+json.dumps(animation)+'})')
    keep_focus=''
    try:
        clients=json.loads(hypr('-j','clients'))
        if animate and not any(c.get('class')=='mpv' and c.get('fullscreen')==2 for c in clients):
            active=json.loads(hypr('-j','activewindow'))
            if isinstance(active,dict) and active.get('address') and active.get('class') not in CLASSES|{'newsboat-youtube-comments'}:
                keep_focus=active['address']
    except (OSError,ValueError,TypeError):pass
    script=('local previous=hl.get_config("misc.on_focus_under_fullscreen"); '
            'hl.config({misc={on_focus_under_fullscreen=0}}); '
            'local ok,err=pcall(function() '
            'hl.dispatch(hl.dsp.workspace.toggle_special("chatterino_chat")) end); '
            'hl.config({misc={on_focus_under_fullscreen=previous}}); '
            'if not ok then error(err) end')
    focus_marker = ROOT / 'media-chat-restore-focus'
    if keep_focus:focus_marker.write_text(keep_focus+'\n')
    instant = ROOT / 'media-chat-slide-instant'
    if not animate:
        instant.write_text('1\n')
    try:
        hypr('eval',script)
    finally:
        focus_marker.unlink(missing_ok=True)
        if not animate:
            instant.unlink(missing_ok=True)


def windowed_chat_path():
    return ROOT / 'media-chat-windowed.json'


def toggle_windowed_chat():
    with (ROOT/'media-chat-windowed.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        _toggle_windowed_chat()


def maintain_windowed_chat(clients):
    with (ROOT/'media-chat-windowed.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        _maintain_windowed_chat(clients)


def _toggle_windowed_chat():
    """Toggle chat without taking keyboard focus from the current app."""
    clients=json.loads(hypr('-j','clients'))
    players=[c for c in clients if c.get('class')=='mpv' and not c.get('fullscreen')]
    players.sort(key=lambda c:c.get('focusHistoryID',999))
    if not players:
        toggle_workspace();return
    player=players[0]
    monitors=json.loads(hypr('-j','monitors'))
    monitor=next((m for m in monitors if m['id']==player['monitor']),None)
    if not monitor or (not player.get('pinned') and monitor.get('activeWorkspace',{}).get('id')!=player.get('workspace',{}).get('id')):return
    visible=any(m.get('specialWorkspace',{}).get('name')=='special:'+WORKSPACE for m in monitors)
    path=windowed_chat_path()
    if visible:path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps({'pid':player['pid'],'address':player['address']}))
        # Allow mouse/keyboard focus to remain on regular application windows.
        hypr('keyword','input:special_fallthrough','1')
    toggle_workspace()


def _maintain_windowed_chat(clients):
    """An explicitly opened chat follows its pinned, windowed player."""
    path=windowed_chat_path()
    try:saved=json.loads(path.read_text())
    except (OSError,ValueError):return
    player=next((c for c in clients if c.get('pid')==saved['pid'] and c.get('address')==saved['address']),None)
    if not player or player.get('fullscreen'):
        path.unlink(missing_ok=True);return
    if not any(c.get('class') in CLASSES|{'newsboat-youtube-comments'} and
               c.get('workspace',{}).get('name')=='special:'+WORKSPACE for c in clients):
        path.unlink(missing_ok=True);return
    monitors=json.loads(hypr('-j','monitors'))
    monitor=next((m for m in monitors if m['id']==player['monitor']),None)
    if not monitor:return
    visible=monitor.get('specialWorkspace',{}).get('name')=='special:'+WORKSPACE
    owner_visible=not player.get('workspace',{}).get('name','').startswith('special:') and (
        player.get('pinned') or monitor.get('activeWorkspace',{}).get('id')==player.get('workspace',{}).get('id'))
    if visible and not owner_visible:
        toggle_on_monitor(monitor,monitors,animate=False)
    elif owner_visible and not monitor.get('specialWorkspace',{}).get('name'):
        toggle_on_monitor(monitor,monitors,animate=False)


def toggle_on_monitor(monitor, monitors, animate=True):
    focused = next((m for m in monitors if m.get('focused')), None)
    if focused and focused['id'] != monitor['id']:
        hypr('dispatch', 'focusmonitor', str(monitor['id']))
    if animate:
        toggle_workspace()
    else:
        toggle_workspace(animate=False)
    if focused and focused['id'] != monitor['id']:
        hypr('dispatch', 'focusmonitor', str(focused['id']))


def hide_workspace(monitors):
    visible = next((m for m in monitors if m.get('specialWorkspace', {}).get('name') == 'special:' + WORKSPACE), None)
    if visible:
        toggle_on_monitor(visible, monitors)


def restore(state, clients, hide=True, animate=False):
    OWNER.unlink(missing_ok=True)
    if 'special_fallthrough' in state:
        hypr('keyword', 'input:special_fallthrough', str(state['special_fallthrough']))
    try:
        panel_space(state,0,animate=animate)
    except (OSError,ValueError):
        pass
    old = state['chat']
    chat = next((c for c in clients if c['address'] == old['address'] and c['pid'] == old['pid']), None)
    if hide:
        hide_workspace(json.loads(hypr('-j', 'monitors')))
        if animate:
            # Keep the full-height pane in place throughout its native slide
            # out. Resizing to the PiP bounds earlier makes it shrink mid-slide.
            # Runs in the chat helper, never on MPV's input/render thread.
            time.sleep(.22)
    if chat:
        style(chat, False)
        move(chat, old)
    STATE.unlink(missing_ok=True)


def leave_fullscreen(pid):
    """Hide chat before the video shrinks, and cancel a pending chat handoff."""
    clients=json.loads(hypr('-j','clients'))
    player=next((c for c in clients if c.get('pid')==pid),None)
    if not player:return
    hide_workspace(json.loads(hypr('-j','monitors')))
    try:(ROOT/'media-chat-cover-cancel').write_text(Path('/tmp/twitch-session.id').read_text().strip())
    except OSError:pass
    with STATE.with_suffix('.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:return
        state=read()
        if state:
            chat=next((c for c in clients if c.get('class') in CLASSES),None)
            remember_theater(player,chat)
            state.pop('transition',None)
            state.update(player=player,socket=socket_for(player),exiting=True)
            if chat and state['chat'].get('pid')!=chat['pid']:state['chat']=chat
            STATE.write_text(json.dumps(state))


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


def remember_theater(player, chat=None):
    saved={'pid': player['pid'], 'address': player['address']}
    if chat:saved['chat']={'pid':chat['pid'],'address':chat['address']}
    PREFERENCE.write_text(json.dumps(saved))
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
    previous=saved.get('chat',{})
    if any(c.get('pid')==previous.get('pid') and c.get('address')==previous.get('address') for c in clients):
        # The existing chat is already loaded: restore it here, without launching
        # another Python opener or rediscovering/reloading the stream's chat.
        if begin(clients, animate=False):
            monitors=json.loads(hypr('-j','monitors'))
            monitor=next((m for m in monitors if m['id']==player['monitor']),None)
            if monitor and monitor.get('specialWorkspace',{}).get('name')!='special:'+WORKSPACE:
                toggle_on_monitor(monitor,monitors,animate=False)
            focus_player()
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
        try:(ROOT/'media-chat-cover-cancel').write_text(Path('/tmp/twitch-session.id').read_text().strip())
        except OSError:pass
        restore(state, clients, animate=True)
        return True


def player_service(player, endpoint):
    from stream_player_identity import chat_identity as identity
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
    panel_space(state,bounds['ratio'])
    STATE.write_text(json.dumps(state))
    owner_tmp = OWNER.with_suffix('.tmp')
    owner_tmp.write_text(f"{player['workspace']['id']} {player['monitor']} {chat.get('workspace', {}).get('id', 0)}\n")
    owner_tmp.replace(OWNER)
    return True


def begin(clients=None, animate=True):
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
            chat = next((c for c in clients if c.get('class') == chat_class and
                         c.get('workspace',{}).get('name')!='special:media_chat_closing'), None)
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
            windowed_chat_path().unlink(missing_ok=True)
            STATE.write_text(json.dumps(state)); STATE.chmod(0o600)
            PREFERENCE.unlink(missing_ok=True)
            owner_tmp = OWNER.with_suffix('.tmp')
            owner_tmp.write_text(f"{player['workspace']['id']} {player['monitor']} {chat.get('workspace', {}).get('id', 0)}\n")
            owner_tmp.replace(OWNER)
            try:
                hypr('keyword', 'input:special_fallthrough', '1')
                panel_space(state,bounds['ratio'],animate=animate)
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
            fcntl.flock(lock,fcntl.LOCK_UN)
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
                remember_theater(player,chat)
            else:
                PREFERENCE.unlink(missing_ok=True)
            restore(state, clients, hide=True)
            return False
        if state.get('exiting'):return True
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
            # Returning to a workspace restores chat, not keyboard focus.
        if not monitor or monitor.get('specialWorkspace', {}).get('name') != 'special:' + WORKSPACE:
            if time.monotonic() - state.get('created', 0) < 1:
                return True
            restore(state, clients, hide=False)
            return False
        bounds = layout(monitor, state.get('service') == 'YouTube' or state['socket'].endswith('mpv-youtube-live-ipc'))
        if chat['at'] != bounds['at'] or chat['size'] != bounds['size']:
            move(chat, bounds)
            panel_space(state,bounds['ratio'])
        return True


def chat_cover_ready(request,state,clients,monitor,ready):
    if not state or state.get('transition'):return False
    if state['player']['pid']==request.get('old_player_pid'):return False
    player=next((c for c in clients if c.get('pid')==state['player']['pid']),None)
    chat=next((c for c in clients if c.get('address')==state['chat']['address']
               and c.get('pid')==state['chat']['pid']),None)
    if not player or not player.get('fullscreen') or not chat:return False
    if monitor.get('specialWorkspace',{}).get('name')!='special:'+WORKSPACE:return False
    bounds=request['bounds']
    return (chat.get('at')==bounds['at'] and chat.get('size')==bounds['size']
            and (chat.get('class')=='com.chatterino.chatterino' or ready(chat['pid'])))


def cover_chat(state,session,monitors):
    """Capture before hiding; wait for the cover to map before tearing chat down."""
    import uuid
    monitor=next((m for m in monitors if m['id']==state['player']['monitor']),None)
    if not monitor or monitor.get('specialWorkspace',{}).get('name')!='special:'+WORKSPACE:return
    bounds=layout(monitor,state.get('service')=='YouTube')
    base=ROOT/('media-chat-cover-'+uuid.uuid4().hex)
    image=str(base)+'.png';ready=str(base)+'.ready';request=str(base)+'.json'
    x,y=bounds['at'];w,h=bounds['size']
    try:
        subprocess.run(['grim','-g',f'{x},{y} {w}x{h}',image],check=True,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        Path(request).write_text(json.dumps(dict(session=session,monitor=monitor,bounds=bounds,
            workspace=state['player']['workspace']['id'],old_player_pid=state['player']['pid'],image=image,ready=ready)))
        subprocess.Popen(['python3',str(Path(__file__).with_name('media-chat-cover.py')),request],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        deadline=time.monotonic()+1
        while time.monotonic()<deadline and not Path(ready).exists():time.sleep(.01)
    except (OSError,subprocess.SubprocessError):
        for name in (image,ready,request):Path(name).unlink(missing_ok=True)


def prepare_transition(session, service, name):
    from stream_preview import capture_switch
    capture_switch(session)
    from stream_sidebar import prepare_transfer
    prepare_transfer(session,service,name)
    with STATE.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read()
        if not state:
            return
        # Keep the outgoing theater intact while resolution/decoding runs.
        # Hiding its special workspace here can unfullscreen the video before
        # the replacement has even captured its mode.
        monitors=json.loads(hypr('-j','monitors'))
        cover_chat(state,session,monitors)
        OWNER.unlink(missing_ok=True)
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
            # A staged player becomes class=mpv before its workspace and
            # fullscreen transaction is finished. Chat must not move or
            # fullscreen that window concurrently with the video handoff.
            if player.get('initialClass') in ('stream-staging','stream-preview') and player['pid']!=state['player']['pid']:
                if ipc(candidate,'get_property','user-data/stream-handoff-complete')!=transition.get('session'):
                    continue
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


def restore_transition_fullscreen(player):
    """Chat teardown can change fullscreen; never trust its earlier snapshot."""
    current=next((c for c in json.loads(hypr('-j','clients'))
                  if c.get('pid')==player['pid'] and c.get('address')==player['address']),None)
    if not current:raise ValueError('Replacement player closed')
    state={'player':current,'socket':socket_for(current)}
    requested=ipc(state,'get_property','fullscreen')
    if current.get('fullscreen')!=2 and requested is True:
        # A compositor-only exit may leave MPV's requested flag true. Clear
        # that stale flag so setting it again emits a fresh Wayland request.
        ipc(state,'set_property','fullscreen',False)
    if current.get('fullscreen')!=2 or requested is not True:
        ipc(state,'set_property','fullscreen',True)
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        current=next((c for c in json.loads(hypr('-j','clients'))
                      if c.get('pid')==player['pid'] and c.get('address')==player['address']),None)
        if not current:raise ValueError('Replacement player closed')
        if current.get('fullscreen')==2:return current
        time.sleep(.01)
    raise ValueError('Replacement fullscreen did not settle')


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
                    # The old chat is replaced by the opener. Do not restore
                    # its windowed geometry or toggle its workspace here: that
                    # tears down the fullscreen canvas underneath the new MPV.
                    OWNER.unlink(missing_ok=True)
                    STATE.unlink(missing_ok=True)
                player=restore_transition_fullscreen(player)
                # The ordinary opener supplies the matching platform's chat and
                # reapplies the fullscreen layout once its window is ready.
                subprocess.run(['python3', str(Path(__file__).with_name('media-chat.py')), '--handoff'], timeout=20)
                return
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        time.sleep(.1)


if __name__ == '__main__':
    import sys
    if sys.argv[1] == 'prepare':
        prepare_transition(*sys.argv[2:])
    elif sys.argv[1] == 'stage-chat':
        prepare_chat_window()
    elif sys.argv[1] == 'retire-chat':
        retire_chat_window(sys.argv[2])
    elif sys.argv[1] == 'place':
        place_player(int(sys.argv[2]))
    elif sys.argv[1] == 'pin':
        place_player(int(sys.argv[2]), align=False)
    elif sys.argv[1] == 'resume':
        resume_transition(sys.argv[2])
