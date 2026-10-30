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
from media_chat_live import live_target
import media_chat_fullscreen as fullscreen_chat

CLASS='newsboat-youtube-comments'
LIVE_CLASS='newsboat-live-chat'
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


def close_panels(clients, panel_class):
    panels=[c for c in clients if c.get('class')==panel_class]
    for panel in panels:
        # Hide before requesting a graceful close so the other panel never
        # shares a visible frame while the old application's shutdown runs.
        hypr('dispatch','movetoworkspacesilent','special:media_chat_closing,address:'+panel['address'])
        hypr('dispatch','closewindow','address:'+panel['address'])
    return bool(panels)


def show_workspace():
    theater = fullscreen_chat.begin(json.loads(hypr('-j', 'clients')))
    monitors=json.loads(hypr('-j','monitors'))
    focused=next((m for m in monitors if m.get('focused')), {})
    if focused.get('specialWorkspace',{}).get('name')!='special:'+WORKSPACE:
        hypr('dispatch','togglespecialworkspace',WORKSPACE)
    if theater:
        fullscreen_chat.focus_player()


def twitch_player(clients):
    from stream_player_identity import identity
    for client in clients:
        if client.get('class', '').lower() != 'mpv':
            continue
        try:
            current = identity(client)
            if current:
                if current[0] == 'Twitch': return current[1], client['pid']
                continue
            process=Path('/proc')/str(int(client['pid']))
            args=process.joinpath('cmdline').read_bytes().split(b'\0')
            if b'--input-ipc-server=/tmp/mpv-twitch-ipc' not in args:
                continue
            env=dict(part.split(b'=',1) for part in process.joinpath('environ').read_bytes().split(b'\0') if b'=' in part)
            # Environment belongs to the first stream when the player is reused.
            import importlib.util
            spec=importlib.util.spec_from_file_location('twitch_ipc',Path(__file__).with_name('twitch-player-ipc.py'))
            ipc=importlib.util.module_from_spec(spec);spec.loader.exec_module(ipc)
            try:name=ipc.channel(client['pid']) or ''
            except (OSError,ValueError):name=''
            name=name or env.get(b'TWITCH_STREAMER_USERNAME',b'').decode()
            if not name:
                import shlex
                for line in Path('/tmp/twitch-stream-context.conf').read_text().splitlines():
                    if line.startswith('STREAMER_USERNAME='):
                        name=shlex.split(line.split('=',1)[1])[0]
            if name:
                return name, client['pid']
        except (OSError,ValueError,IndexError):
            pass
    return None


def main():
    clients=json.loads(hypr('-j','clients'))
    if '--handoff' not in sys.argv and fullscreen_chat.close(clients):return
    active=json.loads(hypr('-j','activewindow'))
    live=live_target(clients,active.get('address'))
    if live and not live['url']:
        subprocess.run(['notify-send','-a','Streams',live['title'],'Chat details are unavailable. Reopen the stream from Mod+Shift+T.'])
        return
    url=live['url'] if live else video_url(clients,active.get('address'))
    panel_class=LIVE_CLASS if live else CLASS
    if not url and active.get('class') in (CLASS,LIVE_CLASS) and not any(c.get('class','').lower()=='mpv' for c in clients):
        hypr('dispatch','togglespecialworkspace',WORKSPACE);return
    if not url:
        close_panels(clients,CLASS)
        close_panels(clients,LIVE_CLASS)
        player=twitch_player(clients)
        if not player:
            # Never resurrect the saved Chatterino layout without a live player.
            close_panels(clients,'com.chatterino.chatterino')
            subprocess.run(['pkill','-x','chatterino'],check=False)
            return
        name,pid=player
        marker=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'twitch-chat-channel-{os.getuid()}'
        try:ready=marker.read_text().strip()==name.lower()
        except OSError:ready=False
        present=any(c.get('class')=='com.chatterino.chatterino' for c in clients)
        if ready and present:
            if fullscreen_chat.begin(clients):
                show_workspace();return
            hypr('dispatch','togglespecialworkspace',WORKSPACE)
            return
        subprocess.run([str(Path(__file__).with_name('twitch-launcher.sh')),
                        '--chat-only',name,str(pid)],check=False)
        for _ in range(80):
            current=json.loads(hypr('-j','clients'))
            if not any(c.get('pid')==pid for c in current):return
            if any(c.get('class')=='com.chatterino.chatterino' for c in current):
                show_workspace()
                return
            time.sleep(.1)
        return
    switched=close_panels(clients,'com.chatterino.chatterino')
    switched=close_panels(clients,CLASS if live else LIVE_CLASS) or switched
    panels=[c for c in clients if c.get('class')==panel_class]
    try:previous=json.loads(STATE.read_text()).get('url')
    except (OSError,ValueError):previous=None
    if panels and previous==url:
        if switched or fullscreen_chat.begin(clients):show_workspace()
        else:hypr('dispatch','togglespecialworkspace',WORKSPACE)
        return
    close_panels(clients,panel_class)
    STATE.write_text(json.dumps({'url':url}));STATE.chmod(0o600)
    command=([sys.executable,str(Path(__file__).with_name('media-live-chat.py')),url,live['title']] if live else
             [sys.executable,str(Path(__file__).with_name('newsboat-youtube-comments.py')),url])
    subprocess.Popen(command,
                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    for _ in range(80):
        if any(c.get('class')==panel_class for c in json.loads(hypr('-j','clients'))):
            show_workspace()
            return
        time.sleep(.1)
    subprocess.run(['notify-send','-a','Newsboat',live['title'] if live else 'YouTube comments','The chat/comments window could not open.'])


if __name__=='__main__':
    with STATE.with_suffix('.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:sys.exit(0)
        if sys.argv[1:]==['--close-youtube']:
            clients=json.loads(hypr('-j','clients'))
            close_panels(clients,CLASS)
            close_panels(clients,LIVE_CLASS)
        else:main()
