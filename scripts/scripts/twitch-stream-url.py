#!/usr/bin/env python3
"""Short-lived Twitch playback URLs, warmed when a picker row is highlighted."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def cached(path):
    try:
        data=json.loads(path.read_text())
        if 0 <= time.time()-data['created'] < 60 and data.get('low') and data.get('best'):
            return data
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return None


def resolve(name, prefetch=False):
    if not re.fullmatch(r'[a-z0-9_]{1,25}',name):
        raise ValueError('Invalid Twitch username')
    root=Path(os.environ['XDG_RUNTIME_DIR'])/'twitch-stream-urls'
    root.mkdir(mode=0o700,exist_ok=True)
    path=root/(name+'.json')
    data=cached(path)
    if data:return data
    with (root/(name+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        data=cached(path)
        if data:return data
        # Avoid flooding Twitch when quickly browsing many rows.
        with (root/'prefetch.lock').open('a') as budget:
            if prefetch:
                try:fcntl.flock(budget,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:return None
            args=['streamlink','--twitch-disable-ads']
            token=Path.home()/'.newsboat/.twitch_oauth'
            if token.exists():args+=['--twitch-api-header','Authorization=OAuth '+token.read_text().strip()]
            result=subprocess.run(args+['--json','https://www.twitch.tv/'+name],
                                  capture_output=True,text=True,timeout=12)
            if result.returncode:raise ValueError('Could not resolve Twitch stream')
            streams=json.loads(result.stdout)['streams']
            quality=next((key for prefix in ('480p','360p') for key in streams if key.startswith(prefix)), 'worst')
            data=dict(created=time.time(),low=streams[quality]['url'],best=streams['best']['url'])
            if not all(data[k].startswith('https://') for k in ('low','best')):
                raise ValueError('Invalid stream URL')
            tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps(data));tmp.chmod(0o600);tmp.replace(path)
            return data


if __name__=='__main__':
    try:
        data=resolve(sys.argv[1].lower(), '--prefetch' in sys.argv)
        if data and '--prefetch' not in sys.argv:
            print(data['best' if '--best' in sys.argv else 'low'])
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired):
        raise SystemExit(1)
