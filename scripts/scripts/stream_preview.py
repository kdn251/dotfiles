"""A cancellable muted MPV preview and an explicit one-shot player handoff."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from mpv_clip import Player

SCRIPTS=Path(__file__).resolve().parent
ROOT=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'stream-preview'
HANDOFF=ROOT/'handoff.json'
CANONICAL=Path('/tmp/mpv-twitch-ipc')
SESSION=Path('/tmp/twitch-session.id')


def clients():
    return json.loads(subprocess.check_output(['hyprctl','-j','clients'],text=True,timeout=2))


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

    def start(self):
        threading.Thread(target=self._run,daemon=True).start()

    def _run(self):
        try:
            url=resolve(self.name,self.service,self.channel)
            if self.cancelled.is_set():return
            from stream_menu_metadata import playback_title
            args=['mpv','--no-terminal','--mute=yes','--force-window=immediate',
                  '--wayland-app-id=stream-preview','--title=Stream preview',
                  '--input-ipc-server='+self.endpoint,'--cache=yes','--cache-secs=30',
                  '--demuxer-max-bytes=384MiB','--demuxer-max-back-bytes=256MiB',
                  '--hwdec=vaapi','--vo=gpu','--gpu-api=opengl',
                  '--script='+str(SCRIPTS/'twitch-first-frame.lua'),
                  '--script='+str(SCRIPTS/'stream-preview.lua'),
                  '--script='+str(SCRIPTS/'stream-title-refresh.lua'),
                  '--force-media-title='+playback_title(self.name,self.service)]
            if self.service in ('Kick','Rumble'):args+=['--user-agent=Mozilla/5.0','--referrer=https://'+self.service.lower()+'.com/']
            if self.service=='YouTube':args+=['--script-opts=ytdl_hook-ytdl_path='+str(Path.home()/'.local/bin/yt-dlp')]
            env=dict(os.environ,STREAM_TITLE_SERVICE=self.service,STREAM_TITLE_NAME=self.name,
                     STREAM_PAGE_URL=self.channel,STREAM_PREVIEW_ACCEPT=str(self.accepted),STREAM_PREVIEW_OWNER=str(os.getpid()))
            if self.service=='Twitch':env['TWITCH_STREAMER_USERNAME']=self.name
            with self.lock:
                if self.cancelled.is_set():return
                self.process=subprocess.Popen(args+[url],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            for _ in range(100):
                if self.cancelled.wait(.05):return
                if self.process.poll() is not None:
                    self.error='Preview unavailable — Enter still opens the stream'
                    return
                window=next((c for c in clients() if c['pid']==self.process.pid),None)
                if window:
                    x,y,w,h=self.bounds
                    subprocess.run(['hyprctl','--batch',f'dispatch setfloating address:{window["address"]}; dispatch resizewindowpixel exact {w} {h},address:{window["address"]}; dispatch movewindowpixel exact {x} {y},address:{window["address"]}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
                    return
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


def adopt(name,title,marker,service,session,page):
    """Consume only the preview explicitly selected by this picker invocation."""
    try:data=json.loads(HANDOFF.read_text())
    except (OSError,ValueError):return None
    if data.get('name','').casefold()!=name.casefold() or data.get('service')!=service or time.time()-data.get('created',0)>70:return None
    p=Player(data['endpoint'],data['pid'])
    try:
        if not p.get('user-data/preview-ready'):return None
        if SESSION.read_text().strip()!=session:return None
        windows=clients()
        old=next((c for c in windows if c.get('class')=='mpv' and c['pid']!=data['pid']),None)
        was_fullscreen=bool(old and old.get('fullscreen'))
        if old:
            try:
                from media_chat_fullscreen import socket_for
                previous=Player(socket_for(old),old['pid'])
                volume=previous.get('volume');previous.close()
                if volume is not None:p.command('set_property','volume',volume)
            except (OSError,ValueError,TypeError):pass
        old_geometry=(old['at'],old['size']) if old and not was_fullscreen else None
        # The launcher already owns the session before the previous player exits.
        if old:
            try:
                fd=os.pidfd_open(old['pid']);signal.pidfd_send_signal(fd,signal.SIGTERM)
                import select
                select.select([fd],[],[],2);os.close(fd)
            except ProcessLookupError:pass
        canonical=CANONICAL
        canonical.unlink(missing_ok=True);canonical.symlink_to(data['endpoint'])
        p.command('set_property','options/wayland-app-id','mpv')
        p.command('set_property','title','${media-title} - mpv')
        # Preserve the already-decoded stream: no loadfile here.
        p.command('script-message','preview-promote',session,page,title,marker)
        HANDOFF.unlink(missing_ok=True)
        for _ in range(20):
            window=next((c for c in clients() if c['pid']==data['pid']),None)
            if window and window.get('class')=='mpv':break
            time.sleep(.025)
        if window:
            address=window['address']
            if old_geometry:
                (x,y),(w,h)=old_geometry
            else:
                monitors=json.loads(subprocess.check_output(['hyprctl','-j','monitors'],timeout=2))
                mon=next(m for m in monitors if m['id']==window['monitor'])
                mw,mh=mon['width']/mon.get('scale',1),mon['height']/mon.get('scale',1)
                w,h=round(mw*.38),round(mw*.21375);x,y=round(mon['x']+mw-w-13),round(mon['y']+mh-h-13)
            subprocess.run(['hyprctl','--batch',f'dispatch resizewindowpixel exact {w} {h},address:{address}; dispatch movewindowpixel exact {x} {y},address:{address}'],stdout=subprocess.DEVNULL,timeout=2)
            from media_chat_fullscreen import place_player
            place_player(data['pid'])
            if was_fullscreen:
                subprocess.run([str(SCRIPTS/'toggle-pip-fullscreen.sh'),'--pid',str(data['pid'])],stdout=subprocess.DEVNULL,timeout=4)
        return data['pid']
    finally:p.close()
