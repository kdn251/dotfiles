"""Publish a small, atomically replaced URL/status index for the native list UI."""
import fcntl
import json
from pathlib import Path
import os
import sqlite3
from contextlib import closing
from newsboat_media import identity, atomic_write, start_time


def publish(state):
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    with (state/'.status.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        statuses = {}
        urls = {}
        for path in state.glob('*.json'):
            try:
                job = json.loads(path.read_text())
                key = identity(job.get('url', ''))
                if not key:
                    continue
                status = job['status']
                if status in {'preparing','downloading','processing'} and (not job.get('process_start') or job.get('process_start') != start_time(job.get('pid', 0))):
                    status = 'failed'
                if status == 'downloading':
                    value = f"↓ {job['percent']:.0f}%" if job.get('percent') is not None else '↓'
                elif status in {'preparing','processing'}:
                    value = '…'
                elif status in {'failed','cancelled'}:
                    value = '✕'
                elif status == 'done' and any(Path(p).is_file() for p in job.get('files', [])):
                    value = '📥'
                else:
                    continue
                statuses[key] = value
                urls[job['url']] = key
            except (OSError, ValueError, KeyError, TypeError):
                continue
        try:
            for path, record in json.loads((state/'.media-index.json').read_text()).items():
                if record.get('valid') and Path(path).is_file():
                    from newsboat_media import filename_identity
                    key = filename_identity(Path(path))
                    if key:
                        statuses.setdefault(key, '📥')
        except (OSError, ValueError):
            pass
        cache = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))
        try:
            with closing(sqlite3.connect(cache.as_uri()+'?mode=ro', uri=True, timeout=1)) as db:
                for (url,) in db.execute('SELECT DISTINCT url FROM rss_item'):
                    key = identity(url)
                    if key in statuses:
                        urls[url] = key
        except sqlite3.Error:
            pass
        content = ''.join(f'{url}\t{statuses[key]}\n' for url,key in sorted(urls.items())
                          if key in statuses and not any(c in url for c in '\t\r\n'))
        target = state.parent/'download-status.tsv'
        if not target.exists() or target.read_text() != content:
            atomic_write(target, content)
