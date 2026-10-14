#!/usr/bin/env python3
"""Keep live chat beside a floating MPV, inside the monitor's usable edges."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

CHAT_CLASSES={'com.chatterino.chatterino','newsboat-live-chat'}

def hypr(*args):
    return subprocess.check_output(['hyprctl',*args],text=True,timeout=2)

def placement(player, chat, monitor, gaps, border):
    width,height=monitor['width'],monitor['height']
    if monitor.get('transform',0)%2:width,height=height,width
    width/=monitor.get('scale',1);height/=monitor.get('scale',1)
    rx,rt,rr,rb=monitor.get('reserved',[0,0,0,0])
    top,right,bottom,left=gaps
    x0=monitor['x']+rx+left+border;y0=monitor['y']+rt+top+border
    x1=monitor['x']+width-rr-right-border;y1=monitor['y']+height-rb-bottom-border
    px,py=player['at'];pw,_=player['size'];cw,ch=chat['size']
    separation=max(2,2*border)
    before=px-cw-separation;after=px+pw+separation
    if before>=x0:x=before
    elif after+cw<=x1:x=after
    else:x=before if px-x0>=x1-(px+pw) else after
    return [round(max(x0,min(x,max(x0,x1-cw)))),round(max(y0,min(py,max(y0,y1-ch))))]

def run():
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))
    with (runtime/f'media-chat-follow-{os.getuid()}.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        cached_until=0;monitors=[];gaps=[12]*4;border=1
        while True:
            delay=.75
            try:
                clients=json.loads(hypr('-j','clients'))
                chats=[c for c in clients if c.get('class') in CHAT_CLASSES and c.get('floating')
                       and c.get('workspace',{}).get('name')=='special:chatterino_chat']
                players=[c for c in clients if c.get('class','').lower()=='mpv' and c.get('floating') and not c.get('fullscreen')]
                players.sort(key=lambda c:c.get('focusHistoryID',999))
                if chats and players:
                    delay=.12
                    if time.monotonic()>=cached_until:
                        monitors=json.loads(hypr('-j','monitors'))
                        raw=json.loads(hypr('-j','getoption','general:gaps_out')).get('custom','12 12 12 12')
                        values=[int(v) for v in raw.split()]
                        if len(values)==4:gaps=values
                        border=json.loads(hypr('-j','getoption','general:border_size')).get('int',1)
                        cached_until=time.monotonic()+2
                    player=players[0]
                    monitor=next((m for m in monitors if m['id']==player['monitor']),None)
                    if monitor:
                        for chat in chats:
                            at=placement(player,chat,monitor,gaps,border)
                            if at!=chat['at']:
                                hypr('dispatch','movewindowpixel',f"exact {at[0]} {at[1]},address:{chat['address']}")
            except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
            time.sleep(delay)

if __name__=='__main__':run()
