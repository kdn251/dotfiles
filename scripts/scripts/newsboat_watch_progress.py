"""Persist resume-position percentages independently of download cleanup."""
from contextlib import closing
import math
import os
from pathlib import Path
import sqlite3
import time
import newsboat_media as media

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'


def record(url, position, duration, sampled_at=None):
    key = media.identity(url)
    if not key or not all(math.isfinite(v) for v in (position, duration)) or duration <= 0 or position < 0:
        return False
    sampled_at = time.time() if sampled_at is None else sampled_at
    if not math.isfinite(sampled_at):
        return False
    STATE.mkdir(parents=True, exist_ok=True)
    with media.library_lock(), closing(sqlite3.connect(STATE/'watch-progress.db')) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS progress (identity TEXT PRIMARY KEY, url TEXT, fraction REAL, updated REAL)')
        columns = {row[1] for row in db.execute('PRAGMA table_info(progress)')}
        for column in ('position', 'duration'):
            if column not in columns:
                db.execute(f'ALTER TABLE progress ADD COLUMN {column} REAL')
        previous = db.execute('SELECT updated FROM progress WHERE identity=?', (':'.join(key),)).fetchone()
        if previous and previous[0] > sampled_at:
            return True  # A newer sample (or explicit reset) already won.
        db.execute('INSERT OR REPLACE INTO progress(identity,url,fraction,updated,position,duration) VALUES (?,?,?,?,?,?)',
                   (':'.join(key), url, min(position/duration, 1), sampled_at,position,duration))
        rows = db.execute('SELECT identity,url,fraction FROM progress').fetchall()
        values = {key: '100%' if fraction >= .95 else f'{int(fraction*100)}%' for key, _, fraction in rows}
        urls = {url: key for key, url, _ in rows}
        for ident, _, _ in rows:
            platform, value = ident.split(':', 1)
            if platform == 'youtube':
                urls['https://www.youtube.com/watch?v='+value] = ident
                urls['https://youtu.be/'+value] = ident
            elif platform == 'twitch':
                urls['https://www.twitch.tv/videos/'+value] = ident
        cache = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))
        try:
            with closing(sqlite3.connect(cache.as_uri()+'?mode=ro', uri=True)) as cached:
                for (link,) in cached.execute('SELECT DISTINCT url FROM rss_item'):
                    identity = media.identity(link)
                    if identity and ':'.join(identity) in values:
                        urls[link] = ':'.join(identity)
        except sqlite3.Error:
            pass
        content = ''.join(f'{url}\t{values[key]}\n' for url, key in sorted(urls.items())
                          if not any(c in url for c in '\t\r\n'))
        from newsboat_playthroughs import with_group_progress
        content = with_group_progress(content)
        target = STATE/'download-status.tsv.watched'
        if not target.exists() or target.read_text() != content:
            media.atomic_write(target, content)
    from newsboat_queue_time import refresh
    refresh()
    return True


def resume_position(url, duration=0, missing=0):
    """Resolve the last position by video identity, across stream/local paths."""
    key = media.identity(url)
    if not key:
        return missing
    path = STATE/'watch-progress.db'
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM progress WHERE identity=?',(':'.join(key),)).fetchone()
        if row is None:
            return missing
        if row['fraction'] >= .999:
            return 0
        position = row['position'] if 'position' in row.keys() else None
        if position is None:
            position = row['fraction'] * duration
        if not math.isfinite(position) or position < 0:
            return 0
        return min(position,max(0,duration-.5)) if duration>0 else position
    except sqlite3.Error:
        return missing
