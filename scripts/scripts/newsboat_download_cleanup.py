"""Delete only explicitly completed, unchanged, unprotected local downloads."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
import newsboat_media as media

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
CONFIG = Path.home()/'.newsboat/download-cleanup.json'


def database():
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE/'watched-downloads.db'
    db = sqlite3.connect(path, timeout=5)
    path.chmod(0o600)
    db.execute('CREATE TABLE IF NOT EXISTS watched(path TEXT PRIMARY KEY,url TEXT,size INTEGER,mtime INTEGER,completed REAL)')
    return db


def record(path, url, fraction):
    path = Path(path)
    if fraction < .9 or not path.is_absolute() or not media.inside(path) or not path.resolve().is_relative_to(media.ROOT.resolve()):
        return False
    if path.suffix.lower() not in media.MEDIA or not path.is_file() or not media.identity(url):
        return False
    stat = path.stat()
    with closing(database()) as db, db:
        db.execute('INSERT OR REPLACE INTO watched VALUES (?,?,?,?,?)', (str(path), url, stat.st_size, stat.st_mtime_ns, time.time()))
    return True


def player_paths():
    result = set()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = proc.joinpath('cmdline').read_bytes().split(b'\0')
            if not any(Path(os.fsdecode(arg)).name in {'mpv','ffmpeg','yt-dlp','streamlink'} for arg in args[:3]):
                continue
            for fd in proc.joinpath('fd').iterdir():
                try:
                    result.add(fd.resolve())
                except OSError:
                    pass
        except OSError:
            pass
    return result


def cleanup(protected_urls, days, now=None):
    if not isinstance(days, int) or days < 1:
        raise ValueError('Retention must be at least one day')
    now = time.time() if now is None else now
    protected = {media.identity(url) for url in protected_urls}
    removed = []
    with media.library_lock(), closing(database()) as db, db:
        busy = player_paths()
        active = {media.identity(job['url']) for _,job in media.records()
                  if job.get('status') in {'preparing','downloading','processing'}
                  and job.get('process_start') and media.start_time(job.get('pid',0)) == job['process_start']}
        for path_text,url,size,mtime,completed in db.execute('SELECT * FROM watched WHERE completed<=?', (now-days*86400,)).fetchall():
            path = Path(path_text)
            key = media.identity(url)
            if key in protected or key in active or path.resolve() in busy:
                continue
            if not path.is_file():
                db.execute('DELETE FROM watched WHERE path=?', (path_text,))
                continue
            if not media.inside(path) or not path.resolve().is_relative_to(media.ROOT.resolve()):
                continue
            stat = path.stat()
            if (stat.st_size,stat.st_mtime_ns) != (size,mtime):
                continue  # Replaced or re-downloaded files need a fresh completed playback.
            if Path(str(path)+'.part').exists() or Path(str(path)+'.ytdl').exists():
                continue
            path.unlink()
            archive = media.ROOT / '.downloaded-twitch-vods'
            if key and key[0] == 'twitch' and archive.exists():
                lines = [line for line in archive.read_text().splitlines() if line.rsplit(':', 1)[-1] != key[1]]
                media.atomic_write(archive, '\n'.join(lines) + ('\n' if lines else ''))
            for suffix in ('.meta','.info.json'):
                sidecar = path.with_suffix(suffix)
                if sidecar.is_file() and media.inside(sidecar):
                    sidecar.unlink()
            db.execute('DELETE FROM watched WHERE path=?', (path_text,))
            removed.append(path_text)
        if removed:
            for state_path,job in media.records():
                previous = job.get('files', [])
                job['files'] = [p for p in previous if p not in removed]
                if previous != job['files']:
                    if not job['files']:
                        job['status'] = 'deleted'
                    media.atomic_write(state_path,json.dumps(job))
            media.rebuild_unlocked()
    return removed
