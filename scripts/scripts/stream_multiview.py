"""Private control channel and geometry for fullscreen multi-stream viewing."""
import json
import os
from pathlib import Path
import re
import socket

ROOT=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/'stream-multiview'
SERVICES={'t':'Twitch','k':'Kick','r':'Rumble','y':'YouTube'}


def typed_stream(text):
    match=re.fullmatch(r'([tkry])/([\w.@-]+)',text.strip(),re.I)
    return {'service':SERVICES[match[1].lower()],'name':match[2].lstrip('@'),'title':''} if match else None


def channel(row):
    service,name=row['service'],row['name']
    names={'YouTube':'youtube_live_channels.tsv','Kick':'kick_channels.tsv','Rumble':'rumble_channels.tsv'}
    if service in names:
        try:
            for line in (Path(__file__).resolve().parent/names[service]).read_text().splitlines():
                parts=line.split()
                if len(parts)>1 and parts[0].casefold()==name.casefold():return parts[1]
        except OSError:pass
    return {'Twitch':'https://www.twitch.tv/','Kick':'https://kick.com/',
            'Rumble':'https://rumble.com/c/','YouTube':'https://www.youtube.com/@'}[service]+name


def cells(count):
    return [(i%2,i//2) for i in range(count)] if count>1 else [(0,0)]


def neighbor(count,index,direction):
    places=cells(count);x,y=places[index]
    dx,dy={'h':(-1,0),'l':(1,0),'k':(0,-1),'j':(0,1)}[direction]
    return next((i for i,p in enumerate(places) if p==(x+dx,y+dy)),index)


def send(pid,action,**data):
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(.2)
            client.connect(str(ROOT/f'{int(pid)}.sock'))
            client.sendall((json.dumps(dict(action=action,**data))+'\n').encode())
        return True
    except (OSError,ValueError):return False


def active(pid=None):
    if not ROOT.exists():return False
    for path in ROOT.glob('*.sock'):
        if pid is not None and path.stem!=str(pid):continue
        if send(path.stem,'ping'):return True
    return False


def mpv_key(name, text='', control=False, alt=False):
    """Translate GTK key symbols without losing uppercase/shifted characters."""
    special={'Return':'ENTER','KP_Enter':'ENTER','Escape':'ESC','space':'SPACE',
             'BackSpace':'BS','Tab':'TAB','Left':'LEFT','Right':'RIGHT','Up':'UP','Down':'DOWN',
             'Delete':'DEL','Home':'HOME','End':'END','Page_Up':'PGUP','Page_Down':'PGDWN'}
    if name in ('Shift_L','Shift_R','Control_L','Control_R','Alt_L','Alt_R','Super_L','Super_R'):return None
    key=special.get(name,text or name)
    if control:key='Ctrl+'+key.lower() if len(key)==1 else 'Ctrl+'+key
    if alt:key='Alt+'+key
    return key
