#!/usr/bin/python
"""Keep OBS's desktop scenes on Hyprland's focused, powered-on display.

Uses OBS's authenticated local WebSocket and the desktop portal's saved
selection API. No screen-picker defaults are changed for other applications.
Stop with: systemctl --user disable --now obs-display-follow.service
"""
import base64
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import time
import uuid

import websocket
from gi.repository import Gio, GLib

HOME = Path.home()
CONFIG = HOME / '.config/obs-studio/plugin_config/obs-websocket/config.json'
NAME = 'monitor (automatic)'
SCENES = ('screen with cam', 'screen with cam with greenscreen', 'laptop no monitor')
LOG = logging.getLogger('obs-display-follow')
STATE = HOME / '.local/state/obs-display-follow'


class OBS:
    def __init__(self):
        config = json.loads(CONFIG.read_text())
        self.ws = websocket.create_connection(
            f"ws://127.0.0.1:{config['server_port']}", timeout=5)
        hello = json.loads(self.ws.recv())['d']
        data = {'rpcVersion': 1, 'eventSubscriptions': 0}
        if 'authentication' in hello:
            auth = hello['authentication']
            secret = base64.b64encode(hashlib.sha256(
                (config['server_password'] + auth['salt']).encode()).digest()).decode()
            data['authentication'] = base64.b64encode(hashlib.sha256(
                (secret + auth['challenge']).encode()).digest()).decode()
        self.ws.send(json.dumps({'op': 1, 'd': data}))
        if json.loads(self.ws.recv())['op'] != 2:
            raise RuntimeError('OBS authentication failed')

    def call(self, kind, **data):
        request_id = str(uuid.uuid4())
        self.ws.send(json.dumps({'op': 6, 'd': {
            'requestType': kind, 'requestId': request_id, 'requestData': data}}))
        while True:
            message = json.loads(self.ws.recv())
            if message['op'] != 7 or message['d']['requestId'] != request_id:
                continue
            reply = message['d']
            if not reply['requestStatus']['result']:
                raise RuntimeError(f"{kind}: {reply['requestStatus'].get('comment')}")
            return reply.get('responseData', {})

    def close(self):
        self.ws.close()


def choose_display(monitors):
    available = [m for m in monitors
                 if not m.get('disabled', False) and m.get('dpmsStatus', True)
                 and m.get('width', 0) > 0 and m.get('height', 0) > 0
                 and m.get('mirrorOf', 'none') in ('none', '')]
    return next((m for m in available if m.get('focused')), next(iter(available), None))


def display():
    result = subprocess.run(['hyprctl', 'monitors', '-j'], capture_output=True,
                            text=True, timeout=3, check=True)
    return choose_display(json.loads(result.stdout))


def signature(monitor):
    return json.dumps([monitor.get(k) for k in
                       ('name', 'width', 'height', 'refreshRate', 'transform', 'scale')])


def portal_call(method, parameters=None, timeout=3000):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return bus.call_sync(
        'org.freedesktop.impl.portal.PermissionStore',
        '/org/freedesktop/impl/portal/PermissionStore',
        'org.freedesktop.impl.portal.PermissionStore', method, parameters,
        None, Gio.DBusCallFlags.NONE, timeout, None)


def selection_token(monitor):
    token = str(uuid.uuid4())
    data = GLib.Variant('(suv)', ('hyprland', 3, GLib.Variant('a{sv}', {
        'output': GLib.Variant('s', monitor['name']),
        'withCursor': GLib.Variant('u', 2),
        'timeIssued': GLib.Variant('t', int(time.time())),
        'token': GLib.Variant('s', 'todo'),
    })))
    # Native OBS is identified by the portal as the empty application ID.
    portal_call('Set', GLib.Variant('(sbsa{sas}v)',
                ('screencast', True, token, {'': ['yes']}, data)))
    return token


def portal_alive():
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync('org.freedesktop.impl.portal.desktop.hyprland',
                      '/org/freedesktop/portal/desktop',
                      'org.freedesktop.DBus.Peer', 'Ping', None, None,
                      Gio.DBusCallFlags.NONE, 2000, None)
        return True
    except GLib.Error:
        return False


def portal_owner():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                         'org.freedesktop.DBus', 'GetNameOwner',
                         GLib.Variant('(s)', ('org.freedesktop.impl.portal.desktop.hyprland',)),
                         None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]


def targets(obs):
    existing = {s['sceneName'] for s in obs.call('GetSceneList')['scenes']}
    return [s for s in SCENES if s in existing]


def source_ready(obs, scene):
    for item in obs.call('GetSceneItemList', sceneName=scene)['sceneItems']:
        if item['sourceName'] == NAME:
            transform = item['sceneItemTransform']
            return transform['sourceWidth'] > 0 and transform['sourceHeight'] > 0
    return False


def create_on_ui(obs, scene, name, settings):
    request_id = str(uuid.uuid4())
    request = {'requestId': request_id, 'scene': scene, 'name': name, 'settings': settings}
    pending = STATE / 'request.tmp'
    pending.write_text(json.dumps(request))
    pending.replace(STATE / 'request.json')
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            response = json.loads((STATE / 'response.json').read_text())
            if response['requestId'] == request_id:
                if not response['ok']:
                    raise RuntimeError('UI capture creation failed')
                items = obs.call('GetSceneItemList', sceneName=scene)['sceneItems']
                return next(i for i in items if i['sourceName'] == name)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(0.25)
    (STATE / 'request.json').unlink(missing_ok=True)
    raise RuntimeError('OBS display bridge is not responding')


def install_capture(obs, monitor, scenes):
    # Stage a new source first, and only replace the old one after frames arrive.
    pending = NAME + ' (connecting)'
    names = {i['inputName'] for i in obs.call('GetInputList')['inputs']}
    if pending in names:
        retired = pending + ' ' + str(uuid.uuid4())
        obs.call('SetInputName', inputName=pending, newInputName=retired)
        obs.call('RemoveInput', inputName=retired)
    token = selection_token(monitor)
    created = create_on_ui(obs, scenes[0], pending,
             {'RestoreToken': token, 'ShowCursor': True,
                            'autoDisplaySignature': signature(monitor),
                            'autoPortalOwner': portal_owner()})
    # Recent OBS builds initialize capture only when the source is showing.
    # Activate it off-canvas in the current scene while verifying the connection.
    active_scene = obs.call('GetCurrentProgramScene')['currentProgramSceneName']
    if active_scene == scenes[0]:
        staging_id = created['sceneItemId']
    else:
        staging_id = obs.call('CreateSceneItem', sceneName=active_scene,
                              sourceName=pending, sceneItemEnabled=False)['sceneItemId']
    obs.call('SetSceneItemTransform', sceneName=active_scene, sceneItemId=staging_id,
             sceneItemTransform={'positionX': -10000, 'positionY': -10000})
    obs.call('SetSceneItemEnabled', sceneName=active_scene, sceneItemId=staging_id,
             sceneItemEnabled=True)
    try:
        deadline = time.monotonic() + 12
        ready = False
        while time.monotonic() < deadline:
            items = obs.call('GetSceneItemList', sceneName=scenes[0])['sceneItems']
            item = next(i for i in items if i['sourceName'] == pending)
            if item['sceneItemTransform']['sourceWidth'] > 0:
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError('Screen capture did not produce frames')
        if NAME in names:
            retired = NAME + ' ' + str(uuid.uuid4())
            obs.call('SetInputName', inputName=NAME, newInputName=retired)
            obs.call('RemoveInput', inputName=retired)
        obs.call('SetInputName', inputName=pending, newInputName=NAME)
        video = obs.call('GetVideoSettings')
        for index, scene in enumerate(scenes):
            if index == 0:
                item_id = item['sceneItemId']
            else:
                item_id = obs.call('CreateSceneItem', sceneName=scene,
                                   sourceName=NAME, sceneItemEnabled=False)['sceneItemId']
            obs.call('SetSceneItemTransform', sceneName=scene, sceneItemId=item_id,
                     sceneItemTransform={'positionX': 0, 'positionY': 0,
                         'alignment': 5, 'boundsType': 'OBS_BOUNDS_SCALE_INNER',
                         'boundsAlignment': 0, 'boundsWidth': video['baseWidth'],
                         'boundsHeight': video['baseHeight']})
            obs.call('SetSceneItemIndex', sceneName=scene, sceneItemId=item_id, sceneItemIndex=0)
            obs.call('SetSceneItemLocked', sceneName=scene, sceneItemId=item_id, sceneItemLocked=True)
            obs.call('SetSceneItemEnabled', sceneName=scene, sceneItemId=item_id, sceneItemEnabled=True)
            for old in obs.call('GetSceneItemList', sceneName=scene)['sceneItems']:
                if old['sourceName'] in ('monitor', 'screen'):
                    obs.call('SetSceneItemEnabled', sceneName=scene,
                             sceneItemId=old['sceneItemId'], sceneItemEnabled=False)
        if active_scene != scenes[0]:
            obs.call('RemoveSceneItem', sceneName=active_scene, sceneItemId=staging_id)
        # The legacy portal source would open another stale session at startup,
        # even when hidden. Remove it only if no unrelated scene uses it.
        if 'monitor' in names:
            unrelated = [s['sceneName'] for s in obs.call('GetSceneList')['scenes']
                         if s['sceneName'] not in scenes]
            referenced = any(any(i['sourceName'] == 'monitor' for i in
                             obs.call('GetSceneItemList', sceneName=s)['sceneItems'])
                             for s in unrelated)
            if not referenced:
                obs.call('RemoveInput', inputName='monitor')
        LOG.info('Capturing %s (%sx%s)', monitor['name'], monitor['width'], monitor['height'])
    except Exception:
        # The original capture remains intact if initialization failed.
        names = {i['inputName'] for i in obs.call('GetInputList')['inputs']}
        if pending in names:
            obs.call('RemoveInput', inputName=pending)
        raise
    finally:
        # The portal consumes this token and supplies OBS with a fresh one.
        try:
            portal_call('Delete', GLib.Variant('(ss)', ('screencast', token)))
        except GLib.Error:
            pass


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    obs = None
    last_health = 0
    last_restart = 0
    needs_reconnect = False
    while True:
        try:
            if obs is None:
                obs = OBS()
            monitor = display()
            scenes = targets(obs)
            if not monitor or not scenes:
                time.sleep(3)
                continue
            now = time.monotonic()
            if now - last_health > 15:
                last_health = now
                if not portal_alive():
                    if now - last_restart < 60:
                        raise RuntimeError('Portal is still unresponsive; waiting before retry')
                    LOG.warning('Screen-sharing portal is unresponsive; restarting it')
                    subprocess.run(['systemctl', '--user', 'restart',
                                    'xdg-desktop-portal-hyprland'], timeout=10, check=True)
                    last_restart = now
                    needs_reconnect = True
                    time.sleep(2)
            names = {i['inputName'] for i in obs.call('GetInputList')['inputs']}
            current = (obs.call('GetInputSettings', inputName=NAME)['inputSettings']
                       if NAME in names else {})
            if (needs_reconnect or current.get('autoDisplaySignature') != signature(monitor)
                    or current.get('autoPortalOwner') != portal_owner()
                    or not source_ready(obs, scenes[0])):
                install_capture(obs, monitor, scenes)
                needs_reconnect = False
            time.sleep(3)
        except (ConnectionRefusedError, FileNotFoundError):
            if obs:
                obs.close()
            obs = None
            time.sleep(5)
        except Exception as error:
            LOG.warning('%s', error)
            if obs:
                try:
                    obs.close()
                except Exception:
                    pass
            obs = None
            time.sleep(15)


if __name__ == '__main__':
    main()
