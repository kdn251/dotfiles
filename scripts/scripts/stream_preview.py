"""A cancellable muted MPV preview and an explicit one-shot player handoff."""
import json
import os
from pathlib import Path
import signal
import select
import runpy
import socket
import subprocess
import sys
import threading
import time
import uuid
from mpv_clip import Player
from stream_player_identity import identity as player_identity

SCRIPTS=Path(__file__).resolve().parent

# Use Lua-compatible IPC even when a resident picker inherited an older PATH.
HYPRCTL = [sys.executable, str(Path(__file__).with_name("hyprctl-compat.py"))]
ROOT=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'stream-preview'
HANDOFF=ROOT/'handoff.json'
CANONICAL=Path('/tmp/mpv-twitch-ipc')
SESSION=Path('/tmp/twitch-session.id')


def clients():
    return json.loads(subprocess.check_output([*HYPRCTL,'-j','clients'],text=True,timeout=2))


def capture_switch(session):
    """Save the selected player's layout before chat/preview work changes it."""
    from media_chat_fullscreen import socket_for
    windows=clients()
    source=int(os.environ.get('STREAM_SWITCH_SOURCE_PID','0'))
    candidates=[c for c in windows if c.get('class')=='mpv']
    if source:candidates=[c for c in candidates if c['pid']==source]
    candidates.sort(key=lambda c:c.get('focusHistoryID',999))
    for old in candidates:
        try:
            player=Player(socket_for(old),old['pid']);player.socket.settimeout(.5)
            try:
                if player.get('user-data/stream-service') not in ('Twitch','YouTube','Kick','Rumble'):continue
                fullscreen=bool(old.get('fullscreen') or player.get('fullscreen'))
            finally:player.close()
            snapshot=dict(session=session,pid=old['pid'],fullscreen=fullscreen,window=old)
            # Enter on an already decoded preview captured the state even
            # earlier, before the picker relinquished keyboard focus.
            try:
                handoff=json.loads(HANDOFF.read_text())
                selected=handoff.get('source')
                if selected and selected['pid']==old['pid'] and time.time()-handoff.get('created',0)<5:
                    snapshot.update(fullscreen=selected['fullscreen'],window=selected['window'])
            except (OSError,ValueError,KeyError):pass
            ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
            path=ROOT/'switch.json';temporary=ROOT/f'switch-{os.getpid()}.tmp'
            temporary.write_text(json.dumps(snapshot));temporary.chmod(0o600);temporary.replace(path)
            return snapshot
        except (OSError,ValueError,TypeError):continue
    return None


def switch_snapshot(session,pid=None):
    try:
        data=json.loads((ROOT/'switch.json').read_text())
        if data.get('session')==session and (pid is None or data.get('pid')==pid):return data
    except (OSError,ValueError):pass
    return None


def already_watching(name, service):
    """Read the live player's identity, not stale launcher/cache metadata."""
    try:
        for window in clients():
            if window.get('class') != 'mpv':continue
            current = player_identity(window)
            if current and current[0] == service and str(current[1]).casefold() == name.casefold():
                return True
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return False


def resolve(name,service,channel):
    command=[sys.executable,str(SCRIPTS/('twitch-stream-url.py' if service=='Twitch' else 'stream-playback-url.py'))]
    command += [name,'--playback'] if service=='Twitch' else [service,channel]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    if result.returncode:raise ValueError('Stream preview unavailable')
    data=json.loads(result.stdout)
    return ('av://hls:'+data['best'] if service=='Twitch' else data.get('playback_url',data['url']))


class Preview:
    def __init__(self,name,service,channel,bounds):
        ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.name,self.service,self.channel=name,service,channel
        self.bounds=bounds
        token=uuid.uuid4().hex
        self.endpoint=str(ROOT/(token+'.sock'))
        self.accepted=ROOT/(token+'.accept')
        self.cancelled=threading.Event()
        self.lock=threading.Lock()
        self.process=None
        self.promoted=False
        self.error=None
        self.landing=None

    def start(self):
        threading.Thread(target=self._run,daemon=True).start()

    def _run(self):
        try:
            if already_watching(self.name,self.service):return
            if self.cancelled.is_set():return
            from stream_menu_metadata import playback_title
            args=['mpv','--no-terminal','--mute=yes','--idle=yes','--force-window=immediate',
                  '--wayland-app-id=stream-preview','--title=Stream preview',
                  '--input-ipc-server='+self.endpoint,'--cache=yes','--cache-secs=30',
                  '--demuxer-max-bytes=384MiB','--demuxer-max-back-bytes=256MiB',
                  '--hwdec=vaapi','--vo=gpu','--gpu-api=opengl',
                  '--script='+str(SCRIPTS/'twitch-first-frame.lua'),
                  '--script='+str(SCRIPTS/'stream-preview.lua'),
                  '--script='+str(SCRIPTS/'stream-title-refresh.lua'),
                  '--force-media-title='+playback_title(self.name,self.service)]
            if self.service in ('Kick','Rumble'):args+=['--user-agent=Mozilla/5.0','--referrer=https://'+self.service.lower()+'.com/']
            if self.service=='YouTube':args+=['--script-opts=ytdl_hook-ytdl_path='+str(Path.home()/'.local/bin/yt-dlp'),
                '--ytdl-raw-options=ignore-config=,no-warnings=,no-playlist=',
                '--demuxer-lavf-o=live_start_index=-1']
            env=dict(os.environ,STREAM_TITLE_SERVICE=self.service,STREAM_TITLE_NAME=self.name,
                     STREAM_PAGE_URL=self.channel,STREAM_PREVIEW_ACCEPT=str(self.accepted),STREAM_PREVIEW_OWNER=str(os.getpid()))
            if self.service=='Twitch':env['TWITCH_STREAMER_USERNAME']=self.name
            with self.lock:
                if self.cancelled.is_set():return
                self.process=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            for _ in range(100):
                if self.cancelled.wait(.05):return
                if self.process.poll() is not None:
                    self.error='Preview unavailable — Enter still opens the stream'
                    return
                window=next((c for c in clients() if c['pid']==self.process.pid),None)
                if window:
                    x,y,w,h=self.bounds
                    subprocess.run([*HYPRCTL,'--batch',f'dispatch setfloating address:{window["address"]}; dispatch resizewindowpixel exact {w} {h},address:{window["address"]}; dispatch movewindowpixel exact {x} {y},address:{window["address"]}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
                    # Prepare geometry while the stream is loading, not on Enter.
                    try:
                        from pip_geometry import monitor_size, bottom_right, settings
                        monitors=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','monitors'],timeout=2))
                        mon=next(m for m in monitors if m['id']==window['monitor'])
                        mw,mh=monitor_size(mon)
                        width,height=round(mw*.38),round(mw*.21375)
                        left,top=bottom_right(mon,(width,height),*settings())
                        self.landing=(window['address'],left,top,width,height)
                    except (OSError,ValueError,KeyError,StopIteration,subprocess.SubprocessError):
                        pass
                    break
            url=resolve(self.name,self.service,self.channel)
            if self.cancelled.is_set():return
            player=Player(self.endpoint,self.process.pid)
            try:player.command('loadfile',url,'replace')
            finally:player.close()
        except (OSError,ValueError,subprocess.SubprocessError) as e:
            self.error='Preview unavailable — Enter still opens the stream'
            self.stop()

    def stop(self):
        self.cancelled.set()
        with self.lock:
            if self.process and not self.promoted and self.process.poll() is None:
                self.process.terminate()
                process=self.process
                def reap():
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                threading.Thread(target=reap,daemon=True).start()
        self.accepted.unlink(missing_ok=True)

    def handoff(self):
        with self.lock:
            if not self.process or self.process.poll() is not None:return False
            try:
                p=Player(self.endpoint,self.process.pid)
                ready=p.get('user-data/preview-ready');p.close()
                if not ready:return False
            except (OSError,ValueError):return False
            data=dict(pid=self.process.pid,endpoint=self.endpoint,name=self.name,service=self.service,created=time.time())
            temp=HANDOFF.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.chmod(0o600);temp.replace(HANDOFF)
            self.promoted=True
            # The decoded preview can move immediately. Session/chat ownership
            # still transfers through the launcher's normal guarded adoption.
            try:
                old = next((c for c in clients() if c.get('class') == 'mpv'
                            and c.get('pid') != self.process.pid), None)
                fullscreen = bool(old and old.get('fullscreen'))
                if old:
                    data['source_pid']=old['pid']
                    data['source']=dict(pid=old['pid'],fullscreen=fullscreen,window=old)
                    temp.write_text(json.dumps(data));temp.chmod(0o600);temp.replace(HANDOFF)
            except (OSError, ValueError, subprocess.SubprocessError):
                fullscreen = True  # Avoid a misplaced flash if layout lookup fails.
            if self.landing and not fullscreen:
                address,x,y,w,h=self.landing
                if old:
                    x,y=old['at']
                    w,h=old['size']
                target=json.dumps('address:'+address)
                script=(f'hl.dispatch(hl.dsp.window.resize({{window={target},x={w},y={h},relative=false}})); '
                        f'hl.dispatch(hl.dsp.window.move({{window={target},x={x},y={y},relative=false}}))')
                try:
                    subprocess.run(['/usr/bin/hyprctl','eval',script],check=True,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=.5)
                    data['landed']=True
                    temp.write_text(json.dumps(data));temp.chmod(0o600);temp.replace(HANDOFF)
                except (OSError,subprocess.SubprocessError):
                    pass
        self.accepted.unlink(missing_ok=True)
        # Failed/cancelled launchers must not leave an orphan preview forever.
        def expire():
            time.sleep(75)
            try:
                if json.loads(HANDOFF.read_text()).get('pid')!=data['pid']:return
                HANDOFF.unlink()
                self.promoted=False;self.stop()
            except (OSError,ValueError):pass
        threading.Thread(target=expire,daemon=True).start()
        return True


class StageFailed(ValueError):
    """Keep the current stream intact if its replacement cannot become ready."""


def stage(name,title,url,marker,fallback,service,session,page,old_pid):
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    endpoint=str(ROOT/(token+'.sock'))
    # Map outside the visible workspace so decoding can finish without exposing
    # a second window or replacing the video currently being watched.
    rule='float on, no_initial_focus on, workspace special:stream_staging silent, match:class ^(stream-staging)$'
    subprocess.run([*HYPRCTL,'keyword','windowrule',rule],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
    args=['mpv','--no-terminal','--mute=yes','--idle=yes','--force-window=immediate',
          '--wayland-app-id=stream-staging','--input-ipc-server='+endpoint,
          '--cache=yes','--cache-secs=30','--demuxer-max-bytes=384MiB','--demuxer-max-back-bytes=256MiB',
          '--hwdec=vaapi','--vo=gpu','--gpu-api=opengl',
          '--script='+str(SCRIPTS/'twitch-first-frame.lua'),
          '--script='+str(SCRIPTS/'stream-preview.lua'),
          '--script='+str(SCRIPTS/'stream-title-refresh.lua'),
          '--force-media-title='+title]
    if service=='YouTube':args+=['--ytdl-raw-options=ignore-config=,no-warnings=,no-playlist=',
        '--demuxer-lavf-o=live_start_index=-1',
        '--script-opts=ytdl_hook-ytdl_path='+str(Path.home()/'.local/bin/yt-dlp')]
    if service in ('Kick','Rumble'):args+=['--user-agent=Mozilla/5.0','--referrer=https://'+service.lower()+'.com/']
    env=dict(os.environ,STREAM_TITLE_SERVICE=service,STREAM_TITLE_NAME=name,STREAM_PAGE_URL=page,
             STREAM_PREVIEW_OWNER=str(os.getpid()),TWITCH_FALLBACK_URL=fallback)
    if service=='Twitch':env['TWITCH_STREAMER_USERNAME']=name
    process=subprocess.Popen([*args,url],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    promoted=False
    try:
        deadline=time.monotonic()+35
        while time.monotonic()<deadline and process.poll() is None:
            if SESSION.read_text().strip()!=session:raise StageFailed('Selection changed')
            if not Path(f'/proc/{old_pid}').exists():raise StageFailed('Player closed')
            try:
                player=Player(endpoint,process.pid)
                try:ready=player.get('user-data/preview-ready')
                finally:player.close()
                if ready:
                    data=dict(pid=process.pid,endpoint=endpoint,name=name,service=service,created=time.time(),staged=True,source_pid=old_pid)
                    tmp=HANDOFF.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.chmod(0o600);tmp.replace(HANDOFF)
                    result=adopt(name,title,marker,service,session,page)
                    if result:promoted=True;return result
                    raise StageFailed('Selection changed')
            except (OSError,ValueError) as error:
                if isinstance(error,StageFailed):raise
            time.sleep(.025)
        raise StageFailed('New stream did not become ready; current stream kept playing')
    finally:
        if not promoted and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill()


def retire_player(player):
    """Unmap the outgoing stream immediately and guarantee its process exits."""
    try:fd=os.pidfd_open(player['pid'])
    except ProcessLookupError:return
    try:
        target=json.dumps('address:'+player['address'])
        try:
            subprocess.run(['/usr/bin/hyprctl','eval',
                'hl.dispatch(hl.dsp.window.move({workspace="special:stream_retired",follow=false,window='+target+'}))'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=.5)
        except (OSError,subprocess.SubprocessError):pass
        try:
            signal.pidfd_send_signal(fd,signal.SIGTERM)
            if not select.select([fd],[],[],.25)[0]:signal.pidfd_send_signal(fd,signal.SIGKILL)
        except ProcessLookupError:pass
    finally:os.close(fd)


def adopt(name,title,marker,service,session,page):
    """Commit a decoded replacement only after its window and panels are ready."""
    try:data=json.loads(HANDOFF.read_text())
    except (OSError,ValueError):return None
    if data.get('name','').casefold()!=name.casefold() or data.get('service')!=service or time.time()-data.get('created',0)>70:return None
    from media_chat_fullscreen import socket_for,place_player
    from media_panel_layout import PROPERTY,FIT
    p=Player(data['endpoint'],data['pid'])
    previous=None;old=None;attached=False;committed=False
    try:
        if not p.get('user-data/preview-ready'):return None
        if SESSION.read_text().strip()!=session:return None
        windows=clients()
        selected=switch_snapshot(session)
        source_pid=data.get('source_pid') or (selected or {}).get('pid') or int(os.environ.get('STREAM_SWITCH_SOURCE_PID','0'))
        candidates=[c for c in windows if c.get('class')=='mpv' and c['pid']!=data['pid']]
        old=next((c for c in candidates if c['pid']==source_pid),None) if source_pid else next(iter(candidates),None)
        if source_pid and not old:raise StageFailed('Player closed')
        was_fullscreen=bool(old and old.get('fullscreen'))
        if old:
            previous=Player(socket_for(old),old['pid'])
            # MPV owns the requested mode; compositor geometry may lag a transition.
            requested_fullscreen=previous.get('fullscreen')
            if isinstance(requested_fullscreen,bool):was_fullscreen=requested_fullscreen
            if selected and selected.get('pid')==old['pid']:
                was_fullscreen=selected['fullscreen']
            volume=previous.get('volume')
            if volume is not None and volume<=0:volume=previous.get('user-data/stream-audible-volume',100)
            if volume is not None:p.command('set_property','volume',volume)
            layout=previous.get(PROPERTY)
            if isinstance(layout,dict) and layout.get('original'):
                p.command('set_property',PROPERTY,layout)
                for key,value in dict(FIT,**{'video-margin-ratio-left':layout.get('left',0),
                                             'video-margin-ratio-right':layout.get('right',0)}).items():
                    p.command('set_property',key,value)
            if previous.get('user-data/stream-sidebar-open') is True:
                previous.command('set_property','user-data/stream-sidebar-replacement',{'pid':data['pid']})
                deadline=time.monotonic()+1
                while time.monotonic()<deadline:
                    if previous.get('user-data/stream-sidebar-attached')==data['pid']:
                        attached=True;break
                    time.sleep(.01)
                if not attached:raise StageFailed('Stream list could not transfer; current stream kept playing. Reopen the list and try again.')
        window=next((c for c in windows if c['pid']==data['pid']),None)
        if not window:raise StageFailed('Replacement window unavailable; current stream kept playing')
        if old and not was_fullscreen:
            geometry=selected['window'] if selected and selected.get('pid')==old['pid'] else old
            (x,y),(w,h)=geometry['at'],geometry['size']
        elif data.get('landed') and not was_fullscreen:
            (x,y),(w,h)=window['at'],window['size']
        else:
            monitors=json.loads(subprocess.check_output([*HYPRCTL,'-j','monitors'],timeout=2))
            mon=next(m for m in monitors if m['id']==window['monitor'])
            from pip_geometry import monitor_size,bottom_right,settings
            mw,mh=monitor_size(mon);w,h=round(mw*.38),round(mw*.21375)
            x,y=bottom_right(mon,(w,h),*settings())
            if old:
                saved=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f"pip-fullscreen-{os.getuid()}-{old['address']}.geometry.return"
                try:
                    saved=json.loads(saved.read_text())
                    if saved.get('pid')==old['pid']:(x,y),(w,h)=saved['at'],saved['size']
                except (OSError,ValueError):pass
        if was_fullscreen:
            # Set fullscreen before changing the preview class: the mpv class
            # has floating-size rules that would otherwise expose a small window.
            saved=dict(window,at=[x,y],size=[w,h],floating=True,pinned=True)
            prefix=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f"pip-fullscreen-{os.getuid()}-{window['address']}"
            Path(str(prefix)+'.geometry').write_text(json.dumps(saved))
            Path(str(prefix)+'.geometry.return').write_text(json.dumps(saved))
            p.command('set_property','fullscreen',True)
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                current=next((c for c in clients() if c.get('pid')==data['pid']),None)
                if current and current.get('fullscreen')==2:break
                time.sleep(.01)
            else:raise StageFailed('Replacement fullscreen did not become ready')
        p.command('set_property','options/wayland-app-id','mpv')
        p.command('set_property','title','${media-title} - mpv')
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            mapped=next((c for c in clients() if c.get('pid')==data['pid']),None)
            if mapped and mapped.get('class')=='mpv' and mapped.get('mapped',True):break
            time.sleep(.01)
        target='address:'+window['address']
        operations=[]
        if not was_fullscreen:
            operations.extend([f'dispatch resizewindowpixel exact {w} {h},{target}',
                               f'dispatch movewindowpixel exact {x} {y},{target}'])
        if data.get('staged') and old:
            operations.append(f'dispatch movetoworkspacesilent {old["workspace"]["name"]},{target}')
        if operations:
            subprocess.run([*HYPRCTL,'--batch','; '.join(operations)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            current=next((c for c in clients() if c.get('pid')==data['pid']),None)
            if current and current.get('mapped',True) and (not was_fullscreen or current.get('fullscreen')==2):break
            time.sleep(.025)
        else:raise StageFailed('Replacement layout did not become ready; current stream kept playing')
        if SESSION.read_text().strip()!=session:raise StageFailed('Selection changed')
        CANONICAL.unlink(missing_ok=True);CANONICAL.symlink_to(data['endpoint'])
        if previous:previous.command('set_property','mute',True)
        p.command('script-message','preview-promote',session,page,title,marker)
        committed=True
        HANDOFF.unlink(missing_ok=True)
        if old:
            retire_player(old)
            for stale in windows:
                if stale.get('class')=='mpv' and stale.get('pid') not in (old['pid'],data['pid']):
                    try:
                        if player_identity(stale):retire_player(stale)
                    except (OSError,ValueError):pass
        # Retiring the old fullscreen surface can cause a late compositor
        # configure to window the replacement. Reconcile after that surface is
        # gone, before placement would pin it as a windowed player.
        if was_fullscreen:
            current=next((c for c in clients() if c.get('pid')==data['pid']),None)
            if not current or current.get('fullscreen')!=2 or p.get('fullscreen') is False:
                p.command('set_property','fullscreen',True)
                deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    current=next((c for c in clients() if c.get('pid')==data['pid']),None)
                    if current and current.get('fullscreen')==2:break
                    time.sleep(.025)
                else:raise StageFailed('Stream loaded but fullscreen restoration failed')
        place_player(data['pid'],align=not bool(old or was_fullscreen or data.get('landed')))
        p.command('set_property','user-data/stream-handoff-complete',session)
        return data['pid']
    except (OSError,ValueError,subprocess.SubprocessError):
        if not committed:
            if attached and old:
                try:
                    p.command('set_property','user-data/stream-sidebar-replacement',{'pid':old['pid']})
                    deadline=time.monotonic()+.5
                    while time.monotonic()<deadline and p.get('user-data/stream-sidebar-attached')!=old['pid']:time.sleep(.01)
                except (OSError,ValueError):pass
            if previous:
                try:previous.command('set_property','mute',False)
                except (OSError,ValueError):pass
            try:os.kill(data['pid'],signal.SIGTERM)
            except ProcessLookupError:pass
        raise
    finally:
        p.close()
        if previous:previous.close()
