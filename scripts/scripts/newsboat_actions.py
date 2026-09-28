"""Short-lived per-item busy markers shared by collection workers and the UI."""
from functools import wraps
import os
from pathlib import Path
import uuid
from newsboat_media import atomic_write


def begin(url, state=None, owner=None, remove=""):
    state = Path(state) if state is not None else Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'newsboat'
    path = state/'actions-pending'/(uuid.uuid4().hex+'.txt')
    atomic_write(path, url+'\n'+str(owner or Path('/proc')/str(os.getpid()))+'\n'+remove+'\n')
    return path


def finish(path):
    if path:
        Path(path).unlink(missing_ok=True)


def busy(function):
    @wraps(function)
    def wrapped(url, *args, **kwargs):
        removing = function.__name__ == 'remove' or (function.__name__ == 'restore' and args and not args[0])
        kind = Path(function.__globals__.get('__file__','')).stem.removeprefix('newsboat-')
        marker = begin(url, function.__globals__.get('STATE'), remove=kind if removing else '')
        try:
            return function(url, *args, **kwargs)
        finally:
            finish(marker)
    return wrapped


def enqueue_collection(script, state, args):
    import json
    import subprocess
    import sys
    import time
    queue=Path(state)/'collection-actions'/Path(script).stem
    queue.mkdir(parents=True,exist_ok=True)
    job=queue/f'{time.time_ns():020d}-{uuid.uuid4().hex}.json'
    marker=None
    try:
        removing=args[0]=='remove' or (args[0]=='restore' and args[2]!='saved')
        kind=Path(script).stem.removeprefix('newsboat-')
        marker=begin(args[1],state,owner=job,remove=kind if removing else '')
        atomic_write(job,json.dumps({'args':args,'pending_marker':str(marker)}))
        subprocess.Popen([sys.executable,script,'work'],stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except Exception:
        finish(marker);job.unlink(missing_ok=True)
        raise


def drain_collection(script, state, handlers):
    import fcntl
    import json
    import subprocess
    queue=Path(state)/'collection-actions'/Path(script).stem
    queue.mkdir(parents=True,exist_ok=True)
    with (queue/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        while jobs:=sorted(queue.glob('*.json')):
            for job in jobs:
                action={}
                try:
                    action=json.loads(job.read_text());args=action['args']
                    if args[0]=='restore':handlers['restore'](args[1],args[2]=='saved')
                    else:handlers[args[0]](args[1])
                except Exception:
                    subprocess.run(['notify-send','-a','Newsboat','-t','5000',
                                    'Collection change failed','Please try the action again.'],check=False)
                finally:
                    finish(action.get('pending_marker'));job.unlink(missing_ok=True)
