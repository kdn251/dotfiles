#!/usr/bin/env python3
"""Short-lived, private playback cache for highlighted live-stream rows."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SERVICES = {'Kick', 'YouTube', 'Rumble'}
TTL = 20


def root():
    directory = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))/'stream-playback-urls'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def cached(path, service, channel):
    try:
        data = json.loads(path.read_text())
        if (data['service'] == service and data['channel'] == channel and
                0 <= time.time()-data['created'] < TTL and
                data['stream']['url'].startswith('https://')):
            return data['stream']
    except (OSError, ValueError, KeyError, TypeError, AttributeError): pass
    return None


def resolve(service, channel, prefetch=False):
    if service not in SERVICES: raise ValueError('Unsupported platform')
    channel = channel.rstrip('/')
    directory = root()
    key = hashlib.sha256((service+'\n'+channel).encode()).hexdigest()
    path = directory/(key+'.json')
    data = cached(path, service, channel)
    if data: return data
    # Speculation never queues up or blocks an unrelated explicit selection.
    with (directory/'prefetch.lock').open('a') as budget, (directory/(key+'.lock')).open('a') as lock:
        if prefetch:
            try: fcntl.flock(budget, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return None
        try: fcntl.flock(lock, fcntl.LOCK_EX | (fcntl.LOCK_NB if prefetch else 0))
        except BlockingIOError: return None
        data = cached(path, service, channel)
        if data: return data
        helper = Path(__file__).with_name(service.lower()+'-live.py')
        result = subprocess.run([sys.executable, str(helper), channel], capture_output=True, text=True, timeout=55)
        if result.returncode: raise ValueError(result.stderr.strip() or 'Could not resolve stream')
        data = json.loads(result.stdout)
        if not str(data.get('url', '')).startswith('https://'): raise ValueError('Invalid stream URL')
        if service == 'Kick':
            from stream_hls import resolve_best
            try:
                selected = resolve_best(data['url'], service)
                if selected != data['url']:
                    data['playback_url'] = selected
            except (OSError, ValueError):
                pass  # The master remains playable if preselection fails.
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(service=service, channel=channel, created=time.time(), stream=data)))
        temp.chmod(0o600)
        temp.replace(path)
        return data


if __name__ == '__main__':
    try:
        result = resolve(sys.argv[1], sys.argv[2], '--prefetch' in sys.argv)
        if result and '--prefetch' not in sys.argv: print(json.dumps(result))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
