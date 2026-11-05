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


def prepare_transfer(session,service,name):
    """Snapshot whether the list is open before the launcher replaces MPV."""
    import json,subprocess,sys
    from media_chat_fullscreen import ipc,socket_for
    try:
        clients=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','clients'],timeout=1))
        for player in clients:
            if player.get('class')!='mpv':continue
            try:
                state={'player':player,'socket':socket_for(player)}
                if not state['socket'] or not ipc(state,'get_property','user-data/stream-sidebar-open'):continue
                subprocess.Popen([sys.executable,__file__,session,service,name,str(player['pid'])],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                return
            except (OSError,ValueError):continue
    except (OSError,ValueError,subprocess.SubprocessError):pass


def transfer(session,service,name,old_pid):
    import json,subprocess,sys,os,fcntl
    from media_chat_fullscreen import ipc,socket_for
    from stream_player_identity import identity
    deadline=time.monotonic()+60
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))
    while time.monotonic()<deadline:
        try:
            if Path('/tmp/twitch-session.id').read_text().strip()!=session:return
            clients=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','clients'],timeout=1))
            old=next((c for c in clients if c.get('pid')==old_pid),None)
            if old:
                try:
                    if ipc({'player':old,'socket':socket_for(old)},'get_property','user-data/stream-sidebar-open') is False:return
                except (OSError,ValueError):pass
            for player in clients:
                if player.get('class')!='mpv' or not player.get('fullscreen'):continue
                current=identity(player)
                if not current or (current[0],current[1].casefold())!=(service,name.casefold()):continue
                # A reused player keeps its existing menu. A replacement player
                # waits for the old menu to exit before opening its own.
                with (runtime/'stream-sidebar.lock').open('a+') as lock:
                    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:
                        if player['pid']==old_pid:return
                        continue
                subprocess.Popen([sys.executable,str(Path(__file__).with_name('stream-sidebar.py')),str(player['pid'])],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                return
        except (OSError,ValueError,subprocess.SubprocessError):pass
        time.sleep(.05)

if __name__=='__main__':
    import sys
    transfer(*sys.argv[1:4],int(sys.argv[4]))
