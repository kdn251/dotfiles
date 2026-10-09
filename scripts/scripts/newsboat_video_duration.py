"""Fetch metadata for visible videos off the UI thread; never download media."""
from contextlib import closing
import json
import queue
import sqlite3
import threading
import time
import newsboat_queue_time as timing
import newsboat_reading_time as reading
from newsboat_playlist_avatars import parse_rows


def key(url):
    ident = timing.media.identity(url)
    return ':'.join(ident) if ident and ident[0] in ('youtube','twitch','twitch-clip') else reading.article_key(url)


def label(seconds):
    seconds = round(timing.positive(seconds))
    if not seconds:return '—'
    hours, seconds = divmod(seconds,3600)
    minutes, seconds = divmod(seconds,60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'


def cached_duration(url):
    ident = key(url)
    if not ident:return 0
    cached = timing.read('queue-durations.json',{}).get(ident,{})
    duration = timing.positive(cached.get('duration'))
    if duration:return duration
    try:
        with closing(sqlite3.connect((timing.state()/'watch-progress.db').as_uri()+'?mode=ro',uri=True,timeout=.05)) as db:
            row=db.execute('SELECT duration FROM progress WHERE identity=?',(ident,)).fetchone()
            if row and timing.positive(row[0]):return timing.positive(row[0])
    except sqlite3.Error:pass
    if ident.startswith('youtube:'):
        try:
            data=json.loads((timing.state()/'youtube-playlists/videos'/(ident.split(':',1)[1]+'.json')).read_text())
            return timing.positive(data.get('duration'))
        except (OSError,ValueError):pass
    return 0


class Durations:
    def __init__(self):
        self.path=timing.state()/'video-durations.tsv'
        self.cache=timing.read('video-durations.json',{})
        self.cache={k:v for k,v in self.cache.items() if not k.startswith('article:') or v.get('reading_version')==2}
        self.aliases={}
        self.wanted=set()
        self.requested=set()
        self.jobs=queue.Queue()
        self.results=queue.Queue()
        self.started=False
        self.dirty=False
        self.previous=None
        self.reading_due=0
        self.reading_fractions={}

    def worker(self):
        while True:
            url=self.jobs.get()
            if url not in self.wanted:
                self.results.put((url,None));continue
            try:
                duration=reading.estimate(url, allow_fetch=True) if key(url).startswith('article:') else cached_duration(url) or timing.resolve_duration(url)
            except Exception:
                duration=0
            self.results.put((url,dict(duration=duration,checked=time.time(),reading_version=2)))

    def update(self,value):
        urls=[request.split('\t',1)[0] for _,_,request in parse_rows(value)]
        self.wanted={url for url in urls if key(url)}
        for url in urls:
            ident=key(url)
            if not ident:continue
            self.aliases[url]=ident
            row=self.cache.get(ident,{})
            if (row.get('duration') and not ident.startswith('article:')) or time.time()-row.get('checked',0)<600:continue
            if url not in self.requested:
                self.requested.add(url);self.jobs.put(url)
        if self.wanted and not self.started:
            self.started=True
            for _ in range(2):threading.Thread(target=self.worker,daemon=True).start()

    def poll(self):
        while not self.results.empty():
            url,row=self.results.get_nowait()
            self.requested.discard(url)
            if row is not None:
                self.cache[key(url)]=row;self.dirty=True
        if self.dirty:
            timing.media.atomic_write(timing.state()/'video-durations.json',json.dumps(self.cache))
            self.dirty=False
        if time.monotonic() >= self.reading_due:
            self.reading_fractions=reading.progress()
            self.reading_due=time.monotonic()+.5
        fractions=self.reading_fractions
        text=''.join(url+'\t'+(reading.label(self.cache[ident].get('duration'),fractions.get(url,0)) if ident.startswith('article:') else label(self.cache[ident].get('duration')))+'\n'
                     for url,ident in self.aliases.items() if ident in self.cache and (not ident.startswith('article:') or self.cache[ident].get('duration')))
        if text!=self.previous:
            timing.media.atomic_write(self.path,text);self.previous=text
