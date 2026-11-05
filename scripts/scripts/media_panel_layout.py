"""One saved video layout shared by the left stream list and right chat."""
import fcntl
import os
from pathlib import Path

PROPERTY='user-data/media-panel-layout'
FIT={'keepaspect':True,'panscan':0,'video-zoom':0,'video-pan-x':0,'video-pan-y':0,
     'video-scale-x':1,'video-scale-y':1,'video-align-x':0,'video-align-y':0,
     'video-margin-ratio-left':0,'video-margin-ratio-right':0,
     'video-margin-ratio-top':0,'video-margin-ratio-bottom':0}

def update(command, pid, side, ratio, fallback=None):
    if fallback:
        # Theater snapshots can be taken while the sidebar is already open.
        # Its reserved margin is not part of the underlying video layout.
        fallback=dict(fallback,**{'video-margin-ratio-left':0})
    lock_path=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'media-panel-layout-{pid}.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:state=command('get_property',PROPERTY)
        except (OSError,ValueError):state=None
        if not isinstance(state,dict) or not isinstance(state.get('original'),dict):
            if not ratio:
                for key,value in (fallback or {}).items():command('set_property',key,value)
                return
            original={key:command('get_property',key) for key in FIT}
            # Upgrade an already-open theater chat without losing its true
            # windowed/fullscreen return settings.
            if fallback:original.update(fallback)
            state={'original':original,'left':0,'right':0}
            other='right' if side=='left' else 'left'
            state[other]=float(command('get_property','video-margin-ratio-'+other) or 0)
        state[side]=max(0,min(.4,ratio))
        if state['left'] or state['right']:
            command('set_property',PROPERTY,state)
            values=dict(FIT,**{'video-margin-ratio-left':state['left'],
                              'video-margin-ratio-right':state['right']})
        else:
            values=state['original']
        for key,value in values.items():command('set_property',key,value)
        if not state['left'] and not state['right']:
            command('set_property',PROPERTY,{})
