#!/usr/bin/env python3
"""Toggle Twitch chat or the current Newsboat video's YouTube comments."""
import json
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
from newsboat_media import identity

CLASS='newsboat-youtube-comments'
WORKSPACE='chatterino_chat'
STATE=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'newsboat-comments-{os.getuid()}.json'


def hypr(*args):
    return subprocess.check_output(['hyprctl',*args],text=True)


def video_url(clients, focused):
    players=[c for c in clients if c.get('class','').lower()=='mpv']
    players.sort(key=lambda c:c.get('address')==focused,reverse=True)
    for client in players:
        try:
            env=dict(part.split(b'=',1) for part in Path(f"/proc/{int(client['pid'])}/environ").read_bytes().split(b'\0') if b'=' in part)
            url=env.get(b'NEWSBOAT_MEDIA_URL',b'').decode()
            key=identity(url)
            if key and key[0]=='youtube':return 'https://www.youtube.com/watch?v='+key[1]
            if client.get('address')==focused:return None
        except (OSError,ValueError):continue
    return None


def main():
    clients=json.loads(hypr('-j','clients'))
    active=json.loads(hypr('-j','activewindow'))
    url=video_url(clients,active.get('address'))
    if not url and active.get('class')==CLASS:
        hypr('dispatch','togglespecialworkspace',WORKSPACE);return
    if not url:
        if any(c.get('class')=='com.chatterino.chatterino' for c in clients):
            hypr('dispatch','togglespecialworkspace',WORKSPACE)
        else:subprocess.Popen(['chatterino'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        return
    panels=[c for c in clients if c.get('class')==CLASS]
    try:previous=json.loads(STATE.read_text()).get('url')
    except (OSError,ValueError):previous=None
    if panels and previous==url:
        hypr('dispatch','togglespecialworkspace',WORKSPACE);return
    for panel in panels:hypr('dispatch','closewindow','address:'+panel['address'])
    STATE.write_text(json.dumps({'url':url}));STATE.chmod(0o600)
    subprocess.Popen([sys.executable,str(Path(__file__).with_name('newsboat-youtube-comments.py')),url],
                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    for _ in range(80):
        if any(c.get('class')==CLASS for c in json.loads(hypr('-j','clients'))):
            monitors=json.loads(hypr('-j','monitors'))
            focused=next((m for m in monitors if m.get('focused')), {})
            if focused.get('specialWorkspace',{}).get('name')!='special:'+WORKSPACE:
                hypr('dispatch','togglespecialworkspace',WORKSPACE)
            return
        time.sleep(.1)
    subprocess.run(['notify-send','-a','Newsboat','YouTube comments','The comments window could not open.'])


if __name__=='__main__':
    with STATE.with_suffix('.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:sys.exit(0)
        main()
