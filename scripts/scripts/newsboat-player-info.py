#!/usr/bin/env python3
"""Small playback indicators and cached chapter metadata for MPV."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from newsboat_media import identity, STATE, CACHE, start_time


def canonical(url):
    key=identity(url)
    if key and key[0]=='youtube':return f'https://www.youtube.com/watch?v={key[1]}'
    return url


def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}


def status(url,path):
    if path and (path.startswith('file://') or '://' not in path):return 'Local'
    url=canonical(url)
    job=read(STATE/(hashlib.sha256(url.encode()).hexdigest()[:24]+'.json'))
    phase=job.get('status')
    if phase in ('preparing','downloading','processing','retrying'):
        if not job.get('process_start') or start_time(job.get('pid',0))!=str(job['process_start']):
            phase=None
    if phase in ('preparing','downloading','processing','retrying','waiting'):
        percent=job.get('percent')
        if phase=='downloading' and isinstance(percent,(float,int)) and math.isfinite(percent):
            return f'Downloading {max(0,min(100,round(percent)))}%'
        return {'processing':'Merging','retrying':'Retrying download','waiting':'Download queued'}.get(phase,'Downloading')
    key=identity(url)
    if key and key[0]=='youtube':
        marker=read(CACHE/(key[1]+'.download.json'))
        try:
            if marker.get('pid') and Path('/proc',str(int(marker['pid']))).exists():return 'Downloading'
        except (ValueError,TypeError):pass
    return 'Streaming'


def chapters(url):
    url=canonical(url)
    key=identity(url)
    if not key or key[0]!='youtube':return []
    target=Path.home()/'.cache/mpv-video-chapters'/(key[1]+'.json')
    if target.exists():return read(target)
    job=read(STATE/(hashlib.sha256(url.encode()).hexdigest()[:24]+'.json'))
    raw=job.get('chapters')
    if raw is None:
        executable=Path.home()/'.local/bin/yt-dlp'
        result=subprocess.run([str(executable) if executable.exists() else 'yt-dlp','--ignore-config',
            '--no-playlist','--skip-download','--socket-timeout','8','--retries','0','--extractor-retries','0',
            '--print','%(chapters)j','--',url],capture_output=True,text=True,timeout=35,check=True)
        raw=json.loads(result.stdout)
    output=[]
    for chapter in raw or []:
        start=chapter.get('start_time')
        if isinstance(start,(float,int)) and math.isfinite(start) and start>=0:
            output.append({'time':start,'title':str(chapter.get('title') or 'Chapter '+str(len(output)+1))})
    output.sort(key=lambda c:c['time'])
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(output));temporary.replace(target)
    return output


if __name__=='__main__':
    try:
        if sys.argv[1]=='status':print(status(*sys.argv[2:4]))
        else:print(json.dumps(chapters(sys.argv[2])))
    except (OSError,ValueError,subprocess.SubprocessError):raise SystemExit(1)
