#!/usr/bin/env python3
"""Persistent back/forward navigation between watched streams."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state')))/'stream-watching'
SCRIPTS = Path(__file__).resolve().parent


def record(state, item):
    rows = state.setdefault('items', [])
    index = state.get('index', len(rows)-1)
    pending = state.pop('pending', None)
    if pending and time.time()-pending['at'] < 90 and rows[pending['index']] == item:
        state['index'] = pending['index']
    elif rows and 0 <= index < len(rows) and rows[index] == item:
        pass
    else:
        state['items'] = (rows[:index+1] + [item])[-100:]
        state['index'] = len(state['items'])-1


def step(state, direction):
    index = state.get('index', -1) + direction
    rows = state.get('items', [])
    if not 0 <= index < len(rows):
        return None
    state['pending'] = {'index': index, 'at': time.time()}
    return rows[index]


def main():
    action=sys.argv[1]
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'history.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=ROOT/'history.json'
        try:state=json.loads(path.read_text())
        except (OSError,ValueError):state={}
        selected=None
        if action=='record':record(state,dict(service=sys.argv[2],name=sys.argv[3]))
        elif action=='step':selected=step(state,int(sys.argv[2]))
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(state));temporary.replace(path)
    if action=='step':
        if selected:
            choice=selected['name']+(' ('+selected['service']+')' if selected['service']!='Twitch' else '')
            subprocess.Popen([str(SCRIPTS/'twitch-launcher.sh'),choice],stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            print('Switching to '+selected['name'])
        else:print('No '+('earlier' if int(sys.argv[2])<0 else 'later')+' stream in history')


if __name__=='__main__':main()
