"""Cached live channels for the fullscreen MPV sidebar; no network on open."""
import time
from pathlib import Path
from stream_menu_metadata import load

SERVICES={'t':'Twitch','y':'YouTube','k':'Kick','r':'Rumble'}

def rows(cache=None, now=None, current=None):
    now=time.time() if now is None else now
    result=[]
    for key,channels in (load() if cache is None else cache).items():
        if key not in SERVICES:continue
        for name,data in channels.items():
            if now-data.get('checked_at',0)>900:continue
            count=data.get('viewer_count')
            count=count if isinstance(count,(int,float)) and not isinstance(count,bool) else None
            result.append(dict(name=name,service=SERVICES[key],
                title=data.get('title') or '',category=data.get('category') or '',
                viewers=count,icon=data.get('icon') or str(Path.home()/'.cache/twitch-profiles'/(name.lower()+'.png'))))
    return sorted(result,key=lambda r:(
        not (current and current[0]==r['service'] and current[1].casefold()==r['name'].casefold()),
        -(r['viewers'] or 0),r['name'].casefold(),r['service']))

def choice(row):
    return row['name']+('' if row['service']=='Twitch' else ' ('+row['service']+')')

class VideoSpace:
    def __init__(self, command, pid, fallback=None):
        self.command=command
        self.pid=pid
        self.active=False
        self.fallback=fallback

    def reserve(self, width, monitor_width):
        from media_panel_layout import update
        update(self.command,self.pid,'left',width/monitor_width,self.fallback)
        self.active=True

    def restore(self):
        if not self.active:return
        self.active=False
        from media_panel_layout import update
        try:update(self.command,self.pid,'left',0)
        except (OSError,ValueError):pass
