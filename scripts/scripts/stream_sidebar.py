"""Cached live channels for the fullscreen MPV sidebar; no network on open."""
import time
from pathlib import Path
from stream_menu_metadata import load

SERVICES={'t':'Twitch','y':'YouTube','k':'Kick','r':'Rumble'}

def sidebar_preferences_path():
    import os
    return Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'stream-watching/sidebar.json'


def load_collapsed():
    import json
    try:
        state=json.loads(sidebar_preferences_path().read_text())
        return isinstance(state,dict) and state.get('collapsed') is True
    except (OSError,ValueError):return False


def save_collapsed(collapsed):
    import json,os,tempfile
    path=sidebar_preferences_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as out:
            temporary=Path(out.name)
            json.dump({'collapsed':bool(collapsed)},out)
        os.replace(temporary,path)
    finally:
        if temporary:temporary.unlink(missing_ok=True)


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

def search_rows(catalog,query):
    from stream_menu_metadata import search_rank
    if not query.strip():return catalog
    ranked=[(search_rank(query,row['name'],row.get('category',''),row.get('title','')),i,row)
            for i,row in enumerate(catalog)]
    return [row for rank,i,row in sorted((item for item in ranked if item[0] is not None),key=lambda item:item[:2])]


def choice(row):
    return row['name']+('' if row['service']=='Twitch' else ' ('+row['service']+')')

def visible_on_workspace(player,monitor):
    """Native Hyprland special workspaces may have no numeric id."""
    if not monitor:return False
    def key(workspace):
        return workspace.get('name') or workspace.get('address') or workspace.get('id')
    current=key(player.get('workspace',{}))
    special=monitor.get('specialWorkspace',{})
    name=special.get('name','')
    if not current:return False
    # A fullscreen player can belong to the active special workspace (for
    # example magic). Its normal workspace is necessarily a different one.
    if current==key(special):return True
    if current!=key(monitor.get('activeWorkspace',{})):return False
    if name and name!='special:chatterino_chat':return current==key(special)
    return True


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


def restore_windowed(player):
    """Restore a promoted player's floating bounds after a direct fullscreen exit."""
    import json,os,subprocess
    from pip_geometry import monitor_size,bottom_right,settings
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))
    saved_path=runtime/f"pip-fullscreen-{os.getuid()}-{player['address']}.geometry.return"
    try:saved=json.loads(saved_path.read_text())
    except (OSError,ValueError):saved={}
    if saved.get('pid')==player['pid']:
        x,y=saved['at'];w,h=saved['size']
    else:
        monitors=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','monitors'],timeout=1))
        monitor=next(m for m in monitors if m['id']==player['monitor'])
        width,height=monitor_size(monitor);w,h=round(width*.38),round(width*.21375)
        x,y=bottom_right(monitor,(w,h),*settings())
    target=json.dumps('address:'+player['address'])
    script=(f'hl.dispatch(hl.dsp.window.resize({{window={target},x={w},y={h},relative=false}})); '
            f'hl.dispatch(hl.dsp.window.move({{window={target},x={x},y={y},relative=false}}))')
    subprocess.run(['/usr/bin/hyprctl','eval',script],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1)


    # Both the sidebar and MPV can restore bounds. Serialize the pin check so
    # their fullscreen notifications cannot toggle an already pinned window off.
    import fcntl
    with (runtime/f"stream-windowed-{player['pid']}.lock").open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        clients=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','clients'],timeout=1))
        current=next((c for c in clients if c.get('pid')==player['pid'] and c.get('address')==player['address']),None)
        if current and not current.get('fullscreen') and not current.get('pinned'):
            subprocess.run(['/usr/bin/hyprctl','eval',f'hl.dispatch(hl.dsp.window.pin({{window={target}}}))'],
                check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1)


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
                if player['pid']!=old_pid:
                    try:
                        # An explicitly closed transferred list must not be
                        # resurrected by this older fallback worker.
                        if ipc({'player':player,'socket':socket_for(player)},'get_property','user-data/stream-sidebar-open') is False:return
                    except (OSError,ValueError):pass
                # A reused player keeps its existing menu. A replacement player
                # waits for the old menu to exit before opening its own.
                with (runtime/'stream-sidebar.lock').open('a+') as lock:
                    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:
                        if player['pid']==old_pid:return
                        try:
                            if ipc({'player':player,'socket':socket_for(player)},'get_property','user-data/stream-sidebar-open'):return
                        except (OSError,ValueError):pass
                        continue
                subprocess.Popen([sys.executable,str(Path(__file__).with_name('stream-sidebar.py')),str(player['pid'])],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                return
        except (OSError,ValueError,subprocess.SubprocessError):pass
        time.sleep(.05)

if __name__=='__main__':
    import sys
    transfer(*sys.argv[1:4],int(sys.argv[4]))
