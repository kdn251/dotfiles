"""Executed transiently over authenticated SSH; never installed on the VPS.
Read-only Herdr API client. Events invalidate snapshots; snapshots own state.
"""
import json
import os
import select
import socket
import sys
import time


def connect(path):
    sock = socket.socket(socket.AF_UNIX)
    sock.settimeout(10)
    sock.connect(os.path.expanduser(path))
    return sock


def request(path, method, params):
    with connect(path) as sock:
        sock.sendall((json.dumps({'id': 'computer', 'method': method, 'params': params}) + '\n').encode())
        with sock.makefile('rb') as stream:
            line = stream.readline(4 * 1024 * 1024)
        value = json.loads(line)
        if 'error' in value:
            raise RuntimeError(value['error'])
        return value['result']


def emit(kind, **kwargs):
    print(json.dumps({'kind': kind, 'time': time.time(), **kwargs}), flush=True)


def main(path):
    # Subscribe first, then use authoritative snapshots, never event payloads,
    # to reconcile. New subscriptions do not replay prior events.
    agents = request(path, 'agent.list', {}).get('agents', [])
    ids = {a['pane_id'] for a in agents if a.get('agent') == 'pi'}
    sock = None
    buf = b''
    first = True
    try:
        while True:
            if sock is None:
                sock = connect(path)
                subs = [{'type': 'pane.' + name} for name in ('created', 'closed', 'agent_detected')]
                subs += [{'type': 'pane.agent_status_changed', 'pane_id': pane} for pane in sorted(ids)]
                sock.sendall((json.dumps({'id': 'watch', 'method': 'events.subscribe', 'params': {'subscriptions': subs}}) + '\n').encode())
                # Any rejection/overrun is fatal: local supervisor reconnects and
                # discards its baseline. Never continue from uncertain history.
                sock.settimeout(10)
                buf = b''
                while b'\n' not in buf:
                    data = sock.recv(65536)
                    if not data:
                        raise RuntimeError('subscription closed before acknowledgement')
                    buf += data
                ack, buf = buf.split(b'\n', 1)
                ack = json.loads(ack)
                if 'error' in ack or ack.get('result', {}).get('type') != 'subscription_started':
                    raise RuntimeError('subscription rejected: ' + str(ack))
                sock.settimeout(None)
            agents = request(path, 'agent.list', {}).get('agents', [])
            # Only Pi with the official lifecycle authority, not screen guesses.
            agents = [a for a in agents if a.get('agent') == 'pi'
                      and a.get('agent_session', {}).get('source') == 'herdr:pi'
                      and a.get('screen_detection_skipped') is True]
            # Public IDs are routing keys, not the tab names shown to the user.
            tab_labels = {}
            for workspace in sorted({a['workspace_id'] for a in agents}):
                tabs = request(path, 'tab.list', {'workspace_id': workspace}).get('tabs', [])
                tab_labels.update({tab['tab_id']: tab.get('label', '') for tab in tabs})
            for agent in agents:
                agent['tab_label'] = tab_labels.get(agent.get('tab_id'), '')
            emit('baseline' if first else 'snapshot', agents=agents)
            first = False
            latest = {a['pane_id'] for a in agents}
            if latest != ids:
                ids = latest
                sock.close()
                sock = None
                continue
            if not buf and not select.select([sock], [], [], 5)[0]:
                continue  # Heartbeat/reconciliation also catches topology changes.
            if b'\n' not in buf:
                data = sock.recv(65536)
                if not data:
                    raise RuntimeError('Herdr subscription closed')
                buf += data
            if len(buf) > 4 * 1024 * 1024:
                raise RuntimeError('event buffer exceeded limit')
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                event = json.loads(line)
                if 'error' in event:
                    raise RuntimeError(event['error'])
            # Coalesce a burst of events into one authoritative refresh.
            time.sleep(0.08)
    finally:
        if sock is not None:
            sock.close()


if __name__ == '__main__':
    main(sys.argv[1])
