#!/usr/bin/env python3
"""Resolve an authorized ongoing Twitch VOD into a seekable playlist snapshot."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urljoin
from urllib.request import urlopen

class Quiet:
    def debug(self,*args):pass
    def warning(self,*args):pass
    def error(self,*args):pass

def snapshot(text, base):
    lines=[]
    duration=0.0
    for line in text.splitlines():
        if line.startswith('#EXTINF:'):duration+=float(line.split(':',1)[1].split(',')[0])
        if line.startswith('#EXT-X-PLAYLIST-TYPE:') or line=='#EXT-X-ENDLIST':continue
        if line and not line.startswith('#'):line=urljoin(base,line)
        else:line=re.sub(r'URI="([^"]+)"',lambda m:'URI="'+urljoin(base,m[1])+'"',line)
        lines.append(line)
    # FFmpeg can seek all segments of a finite snapshot. Only the selected
    # segments are downloaded; refresh the snapshot on subsequent rewind use.
    return '\n'.join(lines+['#EXT-X-ENDLIST','']),duration

def resolve(name):
    import yt_dlp
    if not re.fullmatch(r'[a-zA-Z0-9_]{1,25}',name):raise ValueError('Invalid channel')
    root=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'twitch-dvr-{os.getuid()}'
    root.mkdir(mode=0o700,exist_ok=True)
    cache=root/(name.lower()+'.json')
    try:
        data=json.loads(cache.read_text())
        if time.time()-data['checked_at']<60 and Path(data['path']).is_file():return data
    except (OSError,ValueError,KeyError):pass
    opts={'quiet':True,'no_warnings':True,'logger':Quiet(),'live_from_start':True,
          'skip_download':True,'socket_timeout':8,'retries':1,'extractor_retries':1,'format':'best'}
    token=Path.home()/'.newsboat/.twitch_oauth'
    if token.exists():opts['http_headers']={'Authorization':'OAuth '+token.read_text().strip().removeprefix('oauth:')}
    with yt_dlp.YoutubeDL(opts) as y:info=y.extract_info('https://www.twitch.tv/'+name,download=False)
    if not re.fullmatch(r'v\d+',str(info.get('id',''))) or info.get('live_status')!='is_live':
        raise ValueError('No ongoing broadcast recording available')
    with urlopen(info['url'],timeout=10) as response:text=response.read(8*1024*1024).decode()
    playlist,duration=snapshot(text,info['url'])
    if duration<1:raise ValueError('Recording has no footage')
    path=root/(info['id']+'.m3u8')
    with tempfile.NamedTemporaryFile(mode='w',dir=root,delete=False) as out:
        out.write(playlist);tmp=Path(out.name)
    tmp.replace(path)
    data={'path':str(path),'id':info['id'],'duration':duration,'started_at':info.get('timestamp'), 'checked_at':time.time()}
    with tempfile.NamedTemporaryFile(mode='w',dir=root,delete=False) as out:
        json.dump(data,out);tmp=Path(out.name)
    tmp.replace(cache)
    return data

if __name__=='__main__':
    try:print(json.dumps(resolve(sys.argv[1])))
    except Exception:
        print('Twitch rewind is unavailable for this broadcast.',file=sys.stderr)
        sys.exit(1)
