#!/usr/bin/python
"""Start OpenDeck for Kevin's Stream Deck; recover missing USB/OBS links."""
import json
import logging
import os
from pathlib import Path
import subprocess
import time

import psutil
import websocket

HOME = Path.home()
LOG = logging.getLogger('opendeck-watchdog')
PROFILE = HOME / '.config/opendeck/profiles/sd-AL28K2C85916.json'


def deck_nodes():
    nodes = set()
    for entry in Path('/sys/class/hidraw').glob('hidraw*'):
        try:
            data = (entry / 'device/uevent').read_text()
            if 'HID_ID=0003:00000FD9:0000006D' in data.upper():
                nodes.add('/dev/' + entry.name)
        except OSError:
            pass
    return nodes


def app():
    for p in psutil.process_iter(['name', 'uids']):
        if p.info['name'] == 'opendeck' and p.info['uids'].real == os.getuid():
            return p
    return None


def uses_obs():
    try:
        selected = json.loads(PROFILE.read_text())['selected_profile']
        path = PROFILE.with_suffix('') / (selected + '.json')
        return 'dev.theca11.multiobs.' in path.read_text()
    except (OSError, ValueError, KeyError):
        return False


def restart_managed(process):
    managed_pid = subprocess.check_output(
        ['systemctl', '--user', 'show', 'opendeck.service', '--property=MainPID', '--value'],
        text=True, timeout=5).strip()
    if managed_pid != str(process.pid):
        # A copy opened manually must exit before the supervised instance can
        # take over; OpenDeck otherwise forwards to the existing single instance.
        children = process.children(recursive=True)
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
    subprocess.run(['systemctl', '--user', 'restart', 'opendeck.service'], check=True, timeout=20)


def health(process, nodes):
    opened = set()
    for fd in Path(f'/proc/{process.pid}/fd').iterdir():
        try:
            opened.add(os.readlink(fd))
        except OSError:
            pass
    if not nodes.issubset(opened):
        return 'Stream Deck is connected but OpenDeck has not opened it'
    ports = [c.laddr.port for c in process.net_connections(kind='tcp')
             if c.status == psutil.CONN_LISTEN]
    responsive = False
    for port in sorted(ports):
        try:
            ws = websocket.create_connection(f'ws://127.0.0.1:{port}', timeout=2)
            try:
                # OpenDeck closes unregistered plugin sockets on their first
                # message. A completed upgrade checks responsiveness without
                # impersonating or replacing a real plugin registration.
                responsive = ws.connected
            finally:
                ws.close()
            if responsive:
                break
        except (OSError, websocket.WebSocketException):
            pass
    if not responsive:
        return 'OpenDeck is not responding to local WebSocket connections'
    if uses_obs():
        cfg = json.loads((HOME / '.config/opendeck/settings/dev.theca11.multiobs.sdPlugin.json').read_text())
        if cfg.get('ip1') not in ('localhost', '127.0.0.1', '::1'):
            return None
        port = int(cfg.get('port1') or 4455)
        obs_listening = False
        for p in psutil.process_iter(['name', 'uids']):
            if p.info['name'] == 'obs' and p.info['uids'].real == os.getuid():
                obs_listening = any(c.status == psutil.CONN_LISTEN and c.laddr.port == port
                                    for c in p.net_connections(kind='tcp'))
        if obs_listening:
            connected = False
            for child in [process] + process.children(recursive=True):
                try:
                    connected |= any(c.status == psutil.CONN_ESTABLISHED and c.raddr
                                     and c.raddr.port == port
                                     for c in child.net_connections(kind='tcp'))
                except psutil.Error:
                    pass
            if not connected:
                return 'OBS is available but the OpenDeck OBS plugin is disconnected'
    return None


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    identity = None
    grace_until = 0
    bad_since = None
    last_restart = 0
    while True:
        try:
            nodes = deck_nodes()
            process = app()
            now = time.monotonic()
            if not nodes:
                identity = None
                bad_since = None
            elif process is None:
                LOG.info('Stream Deck connected; starting OpenDeck')
                subprocess.run(['systemctl', '--user', 'start', 'opendeck.service'], check=True, timeout=10)
            else:
                current = (process.pid, tuple(sorted(nodes)))
                if current != identity:
                    identity = current
                    grace_until = now + 45
                    bad_since = None
                if now >= grace_until:
                    problem = health(process, nodes)
                    if problem is None:
                        bad_since = None
                    elif bad_since is None:
                        bad_since = now
                        LOG.warning('%s; allowing time to reconnect', problem)
                    elif now - bad_since >= 30 and now - last_restart >= 120:
                        LOG.warning('%s; restarting OpenDeck', problem)
                        restart_managed(process)
                        last_restart = now
                        bad_since = None
                        identity = None
        except (OSError, ValueError, KeyError, psutil.Error, subprocess.SubprocessError) as error:
            LOG.warning('Health check deferred: %s', error)
        time.sleep(10)


if __name__ == '__main__':
    main()
