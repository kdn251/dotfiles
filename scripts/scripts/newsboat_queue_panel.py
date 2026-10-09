"""Live Queue-head summary for the native title row."""
from contextlib import closing
import sqlite3
import math
import os
from pathlib import Path
import time
import newsboat_queue_time as queue_time


def snapshot(rows=None):
    if rows is None:rows = queue_time.read('viewing-queue.json', [])
    if not rows:
        return None
    row = rows[0]
    key = ':'.join(queue_time.media.identity(row.get('url', '')) or ())
    cached = queue_time.read('queue-durations.json', {}).get(key, {})
    duration = max(queue_time.positive(row.get('duration')), queue_time.positive(cached.get('duration')))
    fraction = 0.0
    try:
        with closing(sqlite3.connect((queue_time.state()/'watch-progress.db').as_uri()+'?mode=ro', uri=True, timeout=.02)) as db:
            db.row_factory = sqlite3.Row
            progress = db.execute('SELECT * FROM progress WHERE identity=?', (key,)).fetchone()
            if progress:
                fraction = min(1, max(0, float(progress['fraction'] or 0)))
                if 'duration' in progress.keys():
                    duration = max(duration, queue_time.positive(progress['duration']))
    except sqlite3.Error:
        pass
    return (row.get('title') or 'Untitled video', row.get('source') or 'Unknown creator', fraction, duration)


def clock(seconds):
    seconds = max(0, round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'



class Header:
    def __init__(self):
        self.path = queue_time.state()/'queue-title-progress.tsv'
        self.due = 0

    def update(self):
        if time.monotonic() < self.due:
            return
        self.due = time.monotonic()+.5
        rows = queue_time.read('viewing-queue.json', [])
        value = snapshot(rows)
        path = Path(os.environ.get('NEWSBOAT_QUEUE_STATUS',str(queue_time.state()/'viewing-queue.tsv'))+'.snooze')
        try:deadline = int(path.read_text().strip())
        except (OSError,ValueError):deadline = None
        if deadline and not value:value = ('Timed snooze', '', 0, 0)
        text = ''
        if value:
            title, creator, fraction, duration = value
            clean = lambda text: ' '.join(str(text).split())
            filled = min(8, round(fraction*8))
            bar = '━'*filled+'─'*(8-filled)
            remaining = clock(duration*(1-fraction))+' left' if duration else 'time unknown'
            stop = next((i for i, row in enumerate(rows) if row.get('stop_after')), None)
            if stop is not None:
                seconds, unknown = queue_time.remaining(rows[:stop+1])
                if unknown:
                    remaining = '💤 Stop time unknown'
                else:
                    remaining = '💤 Stops in ' + queue_time.label(seconds, 0, stop+1)
            if deadline:
                minutes = max(0, math.ceil((deadline-time.time())/60))
                hours, minutes = divmod(minutes, 60)
                duration = (f'{hours}h ' if hours else '') + (f'{minutes}m' if minutes or not hours else '')
                remaining = f'💤 {duration.strip()} left'
                if stop is not None:remaining += f' · after #{stop+1}'
            url = rows[0]['url'] if rows else ''
            text = f'{clean(title)}\t{clean(creator)}\t{bar} {fraction:.0%} · {remaining}\t{clean(url)}\n'
        try:
            previous = self.path.read_text()
        except OSError:
            previous = None
        if previous != text:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            queue_time.media.atomic_write(self.path, text)
