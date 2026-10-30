#!/usr/bin/env python3
"""Save a short buffered clip from the MPV window that invoked Shift+C."""
import datetime
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import tempfile


class Player:
    def __init__(self, endpoint, expected_pid=None):
        self.socket=socket.socket(socket.AF_UNIX)
        self.socket.settimeout(60)
        try:
            self.socket.connect(endpoint)
        except OSError:
            self.socket.close()
            raise
        pid,uid,_=struct.unpack('3i',self.socket.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid!=os.getuid() or (expected_pid is not None and pid!=expected_pid):
            self.socket.close()
            raise ValueError('The player has changed; try Shift+C again.')
        self.stream=self.socket.makefile('rwb',buffering=0)
        self.request=0

    def command(self,*args):
        self.request+=1
        self.stream.write((json.dumps({'command':args,'request_id':self.request})+'\n').encode())
        for line in self.stream:
            reply=json.loads(line)
            if reply.get('request_id')==self.request:
                if reply.get('error')!='success': raise ValueError(reply.get('error','MPV command failed'))
                return reply.get('data')
        raise ValueError('The player closed before the clip finished.')

    def get(self,key,default=None):
        try:return self.command('get_property',key)
        except ValueError:return default

    def close(self):
        self.stream.close();self.socket.close()


def clip_range(position, length, ranges):
    if not math.isfinite(position) or not math.isfinite(length) or length<=0:
        raise ValueError('Invalid clip length or playback position.')
    # Seekable ranges are unordered and may have gaps. Use the one containing
    # the current frame, rather than clipping an old stream/seek position.
    merged=[]
    for entry in sorted(ranges,key=lambda r:r['start']):
        entry=dict(entry)
        if merged and entry['start']<=merged[-1]['end']+.001:
            merged[-1]['end']=max(merged[-1]['end'],entry['end'])
        else:merged.append(entry)
    containing=[r for r in merged if r['start']<=position<=r['end']+.25]
    if not containing:raise ValueError('No buffered video at the current position yet.')
    earliest=min(r['start'] for r in containing)
    start=max(0,earliest,position-length)
    if position-start<2:raise ValueError('Less than 2 seconds buffered—try again shortly.')
    return start,position


def avatar(player):
    name=player.get('user-data/stream-name','')
    service=player.get('user-data/stream-service','')
    if service=='Twitch' and re.fullmatch(r'[\w]{1,25}',name):
        path=Path.home()/'.cache/twitch-profiles'/f'{name.lower()}.png'
        if path.is_file():return str(path)
        from stream_profile import cache_avatar
        return cache_avatar('https://www.twitch.tv/'+name.lower(),'')
    if service in ('Kick','Rumble','YouTube'):
        try:
            data=json.loads((Path.home()/f'.cache/{service.lower()}-live-player.json').read_text())
            if data.get('name','').casefold()==name.casefold() and Path(data.get('icon','')).is_file():
                return data['icon']
        except (OSError,ValueError):pass
    return ''


def save(player, directory, length=30):
    position=player.get('time-pos')
    if position is None:raise ValueError('Nothing is playing yet.')
    state=player.get('demuxer-cache-state',{}) or {}
    start,end=clip_range(float(position),length,state.get('seekable-ranges',[]))
    tracks=[t for t in player.get('track-list',[]) if t.get('selected')]
    expected={t['type'] for t in tracks if t.get('type') in ('video','audio')}
    # MKV also supports VP9/AV1/Opus and avoids forcing YouTube codecs into MP4.
    codecs={t.get('codec') for t in tracks if t.get('type') in ('video','audio')}
    extension='.mp4' if codecs and codecs<={'h264','hevc','aac','mp3'} else '.mkv'
    title=player.get('media-title','stream') or 'stream'
    name=re.sub(r'[^\w -]','',title).strip()[:60] or 'stream'
    directory.mkdir(parents=True,exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    fd,path=tempfile.mkstemp(prefix=f'{name}_{stamp}_',suffix=extension,dir=directory)
    os.close(fd)
    output=Path(path)
    try:
        player.command('dump-cache',start,end,str(output))
        result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(output)],capture_output=True,text=True,timeout=15,check=True)
        actual={track['codec_type'] for track in json.loads(result.stdout).get('streams',[])}
        if not expected or not expected.issubset(actual) or output.stat().st_size==0:
            raise ValueError('The buffer did not contain complete video/audio; no incomplete clip was saved.')
        return output,end-start
    except Exception:
        output.unlink(missing_ok=True)
        raise


def note(message,icon='',error=False):
    args=['notify-send','-a','Clip','-t','5000','-u','normal' if not error else 'critical']
    if icon:args+=['-i',icon]
    subprocess.run(args+['Clip',message],check=False)


def main(args):
    player=None
    icon=''
    try:
        if args:
            endpoint=args[0]
            pid=int(args[1]) if len(args)>1 else None
        else:
            focused=json.loads(subprocess.check_output(['hyprctl','-j','activewindow'],text=True))
            if focused.get('class','').lower()!='mpv':raise ValueError('Focus the MPV window you want to clip.')
            pid=int(focused['pid'])
            process_args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
            endpoint=next((arg.decode().split('=',1)[1] for arg in process_args if arg.startswith(b'--input-ipc-server=')),'/tmp/mpv-yt-ipc')
        player=Player(endpoint,pid)
        icon=avatar(player)
        output,duration=save(player,Path(os.environ.get('CLIP_DIR',str(Path.home()/'Videos/clips'))),float(args[2] if len(args)>2 else os.environ.get('CLIP_LENGTH','30')))
        note(f'Saved {duration:.0f}s — {output.name}',icon)
        return 0
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        note(str(error),icon,error=True)
        return 1
    finally:
        if player:player.close()


if __name__=='__main__':
    sys.exit(main(sys.argv[1:]))
