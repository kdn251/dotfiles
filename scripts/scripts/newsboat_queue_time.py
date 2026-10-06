"""Cached, nonblocking remaining watch time for the homepage Queue row."""
from contextlib import closing
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import newsboat_media as media


def state():
    return Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'newsboat'


def read(name,default):
    try:return json.loads((state()/name).read_text())
    except (OSError,ValueError):return default


def positive(value):
    try:
        value=float(value)
        return value if math.isfinite(value) and value>0 else 0
    except (ValueError,TypeError):return 0


def remaining(rows):
    durations=read('queue-durations.json',{})
    progress={}
    try:
        with closing(sqlite3.connect((state()/'watch-progress.db').as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
            db.row_factory=sqlite3.Row
            progress={row['identity']:(row['fraction'],row['duration'] if 'duration' in row.keys() else 0) for row in db.execute('SELECT * FROM progress')}
    except sqlite3.Error:pass
    total=0;unknown=[]
    for row in rows:
        key=':'.join(media.identity(row['url']) or ())
        fraction,duration=progress.get(key,(0,0))
        duration=max(positive(duration),positive(durations.get(key,{}).get('duration')),positive(row.get('duration')))
        if duration:
            total+=duration*(1-min(1,max(0,float(fraction or 0))))
        else:unknown.append(row['url'])
    return total,unknown


def label(seconds,unknown,count):
    if not count:return ''
    if unknown==count:return 'time unavailable'
    if seconds<=0:text='0 min'
    elif seconds<60:text='<1 min'
    else:
        minutes=math.ceil(seconds/60-1e-9)
        hours,minutes=divmod(minutes,60)
        text=(f'{hours}h ' if hours else '')+(f'{minutes} min' if minutes else '')
        text=text.strip()
    return ('about ' if seconds>=60 else '')+text+' remaining'+(f' · {unknown} unknown' if unknown else '')


def publish(rows):
    seconds,unknown=remaining(rows)
    text=label(seconds,len(unknown),len(rows))+'\n'
    path=state()/'viewing-queue.tsv.time'
    if not path.exists() or path.read_text()!=text:media.atomic_write(path,text)
    return unknown


def refresh():
    state().mkdir(parents=True,exist_ok=True)
    with (state()/'viewing-queue.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return publish(read('viewing-queue.json',[]))


def start_worker():
    subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'resolve'],stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def resolve_duration(url):
    local=media.playback_file(url)
    if local:
        cmd=['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(local)]
    else:
        executable=Path.home()/'.local/bin/yt-dlp'
        cmd=[str(executable) if executable.exists() else 'yt-dlp','--ignore-config','--no-playlist',
             '--skip-download','--print','duration','--socket-timeout','8','--retries','0','--extractor-retries','0','--',url]
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        return positive(result.stdout.strip()) if result.returncode==0 else 0
    except (OSError,subprocess.TimeoutExpired):return 0


def resolve():
    state().mkdir(parents=True,exist_ok=True)
    with (state()/'queue-duration-worker.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        while True:
            unknown=refresh();cache=read('queue-durations.json',{})
            pending=[u for u in unknown if time.time()-cache.get(':'.join(media.identity(u) or ()),{}).get('checked',0)>300]
            if not pending:return
            url=pending[0];duration=resolve_duration(url)
            cache[':'.join(media.identity(url) or ())]=dict(duration=duration,checked=time.time())
            media.atomic_write(state()/'queue-durations.json',json.dumps(cache))


if __name__=='__main__':resolve()
