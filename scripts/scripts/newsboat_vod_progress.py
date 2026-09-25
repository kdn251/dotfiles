"""Small snapshots of active scheduled VOD downloads; no whole-file probing."""
import json
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
from newsboat_media import atomic_write, filename_identity, ROOT

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
DIRECTORY = ROOT/'twitch-vods'


def active_rows():
    rows = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = proc.joinpath('cmdline').read_bytes().decode(errors='replace').split('\0')
            if not any(Path(arg).name == 'streamlink' for arg in args[:3]) or '--output' not in args:
                continue
            path = Path(args[args.index('--output')+1])
            if path.parent.resolve() != DIRECTORY.resolve():
                continue
            key = filename_identity(path)
            if not key or key[0] != 'twitch':
                continue
            source, _, title = path.stem.partition(' - ')
            rows.append(dict(id=key[1],url='https://www.twitch.tv/videos/'+key[1],
                title=title.rsplit(' - ',1)[0],source=source,path=str(path),
                saved=path.stat().st_mtime if path.exists() else time.time(),active=True))
        except (OSError,IndexError):
            continue
    return rows


def pcrs(data):
    """Read transport-stream clocks from a bounded head/tail sample."""
    first = next((i for i in range(min(188,len(data)-188))
                  if data[i] == 0x47 and data[i+188] == 0x47), None)
    if first is None:
        return []
    clocks = []
    for start in range(first,len(data)-187,188):
        p = data[start:start+188]
        if p[0] != 0x47 or not p[3]&0x20 or p[4]<7 or not p[5]&0x10:
            continue
        pid = ((p[1]&31)<<8)|p[2]
        base = (p[6]<<25)|(p[7]<<17)|(p[8]<<9)|(p[9]<<1)|(p[10]>>7)
        clocks.append((pid,base))
    return clocks


def downloaded_seconds(path):
    try:
        with Path(path).open('rb') as stream:
            head = pcrs(stream.read(1024*1024))
            stream.seek(max(0,os.fstat(stream.fileno()).st_size-1024*1024))
            tail = pcrs(stream.read(1024*1024))
        if not head or not tail:
            return None
        pid,start = head[0]
        end = next((clock for stream_pid,clock in reversed(tail) if stream_pid==pid), None)
        return ((end-start) % (1<<33))/90000 if end is not None else None
    except OSError:
        return None


def get_duration(row):
    cache = STATE/'vod-durations'/f"{row['id']}.json"
    try:
        value = json.loads(cache.read_text())
        if value.get('duration') or time.time()-value.get('checked',0)<300:
            return value.get('duration')
    except (OSError,ValueError):
        pass
    duration = None
    try:
        executable = Path.home()/'.local/bin/yt-dlp'
        result = subprocess.run([str(executable) if executable.exists() else 'yt-dlp',
            '--skip-download','--no-playlist','--no-warnings','--print','duration',row['url']],
            capture_output=True,text=True,timeout=20)
        if result.returncode==0:
            duration = float(result.stdout.strip())
            if duration<=0:duration=None
    except (OSError,ValueError,subprocess.TimeoutExpired):
        pass
    atomic_write(cache,json.dumps(dict(duration=duration,checked=time.time())))
    return duration


def label(row, duration=None):
    seconds = downloaded_seconds(row['path']) if duration else None
    if seconds is not None:
        return f'↓ {min(99,max(0,int(seconds/duration*100)))}%'
    try:
        size=Path(row['path']).stat().st_size
    except OSError:
        size=0
    return f'↓ {size/1024**3:.1f}GB' if size>=1024**3 else f'↓ {size/1024**2:.0f}MB'


def publish_count(active, state=None):
    state = Path(state) if state is not None else STATE
    urls = {row['url'] for row in active}
    try:
        completed = json.loads((state/'vod-items.json').read_text())
    except (OSError, ValueError):
        completed = []
    for row in completed:
        path = Path(row['path'])
        if path.is_file() and not any(Path(str(path)+suffix).exists() for suffix in ('.part','.ytdl','.incomplete')):
            urls.add(row['url'])
    target = state/'starred-urls.txt.vods.count'
    content = str(len(urls))+'\n'
    if not target.exists() or target.read_text()!=content:
        atomic_write(target,content)
    return len(urls)


def publish(rows, durations):
    publish_count(rows)
    path=STATE/'download-status.tsv.vods'
    content=''.join(row['url']+'\t'+label(row,durations.get(row['id']))+'\n' for row in rows)
    if not path.exists() or path.read_text()!=content:
        atomic_write(path,content)


def parent_alive(pid):
    if pid is None:
        return True
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:
        return False


def monitor(parent=None):
    STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/'vod-progress.lock').open('a') as lock:
        while parent_alive(parent):
            try:
                fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if parent is None:
                    return
                time.sleep(2)
        else:
            return
        durations={}
        previous={}
        while parent_alive(parent):
            rows=active_rows()
            by_url={row['url']:row for row in rows}
            publish(rows,durations)
            for row in rows:
                if row['id'] not in durations:
                    durations[row['id']]=get_duration(row)
            publish(rows,durations)
            # A failed partial must never acquire the completed-download badge.
            failed=[row for url,row in previous.items() if url not in by_url
                    and (not Path(row['path']).is_file() or Path(row['path']+'.incomplete').exists())]
            if failed:
                path=STATE/'download-status.tsv.vods'
                atomic_write(path,path.read_text()+''.join(row['url']+'\t✕\n' for row in failed))
            previous.update(by_url)
            if not rows and parent is None:
                return
            time.sleep(2)


if __name__ == '__main__':
    monitor(int(sys.argv[1]) if len(sys.argv)>1 else None)
