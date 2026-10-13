"""Publication dates for visible playlist videos, fetched off the UI thread."""
from datetime import datetime
import json
import queue
import re
import threading
import time
from urllib.request import Request, urlopen
import newsboat_queue_time as timing
from newsboat_playlist_avatars import parse_rows


CACHE_VERSION = 2


def parse_date(value):
    if not isinstance(value, str):return ''
    try:return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except ValueError:pass
    # Request English metadata and parse independently of the terminal's locale.
    match=re.search(r'\b([A-Z][a-z]{2}) (\d{1,2}), (\d{4})\b',value)
    if match:
        months='Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
        try:return datetime(int(match[3]),months.index(match[1])+1,int(match[2])).strftime('%Y-%m-%d')
        except ValueError:pass
    return ''


def date_from_page(page):
    # Player microformat uses ISO dates. When playback requires sign-in, the
    # watch-page header still supplies the public date as a text object.
    decoder=json.JSONDecoder()
    for field in ('publishDate', 'uploadDate'):
        for match in re.finditer(r'"'+field+r'"\s*:\s*',page):
            try:value=decoder.raw_decode(page,match.end())[0]
            except ValueError:continue
            if isinstance(value,dict):
                value=value.get('simpleText') or ''.join(r.get('text','') for r in value.get('runs',[]))
            date=parse_date(value)
            if date:return date
    # Only inspect the current video's primary information, never dates of
    # recommended videos elsewhere on the page.
    for match in re.finditer(r'"videoPrimaryInfoRenderer"\s*:\s*',page):
        try:info=decoder.raw_decode(page,match.end())[0]
        except ValueError:continue
        value=info.get('dateText',{})
        date=parse_date(value.get('simpleText') or ''.join(r.get('text','') for r in value.get('runs',[])))
        if date:return date
    return ''


def display_date(value):
    """Include the year for older playlist videos without inventing a publish time."""
    try:return datetime.strptime(value, '%Y-%m-%d').strftime('%b %d %Y')
    except (ValueError, TypeError):return '—'


def video_id(url):
    key=timing.media.identity(url)
    return key[1] if key and key[0]=='youtube' else None


def lookup(url):
    ident=video_id(url)
    if not ident:return ''
    try:
        row=json.loads((timing.state()/'youtube-playlists/videos'/(ident+'.json')).read_text())
        if row.get('published'):return datetime.fromtimestamp(float(row['published'])).strftime('%Y-%m-%d')
    except (OSError,ValueError,TypeError,OverflowError):pass
    with urlopen(Request('https://www.youtube.com/watch?v='+ident+'&hl=en',headers={'User-Agent':'Mozilla/5.0','Accept-Language':'en-US,en;q=0.9'}),timeout=8) as response:
        return date_from_page(response.read(5*1024*1024).decode('utf-8',errors='replace'))


class Dates:
    def __init__(self):
        self.path=timing.state()/'video-dates.tsv'
        self.cache={key:row for key,row in timing.read('video-dates.json',{}).items()
                    if row.get('date') or row.get('version')==CACHE_VERSION}
        self.aliases={};self.wanted=set();self.requested=set()
        self.jobs=queue.Queue();self.results=queue.Queue();self.started=False;self.previous=None

    def worker(self):
        while True:
            url=self.jobs.get()
            if url not in self.wanted:self.results.put((url,None));continue
            try:date=lookup(url)
            except Exception:date=''
            self.results.put((url,dict(date=date,checked=time.time(),version=CACHE_VERSION)))

    def update(self,value):
        urls=[request.split('\t',1)[0] for _,_,request in parse_rows(value)]
        self.wanted={u for u in urls if video_id(u) and
                     (timing.state()/'youtube-playlists/videos'/(video_id(u)+'.json')).exists()}
        for url in urls:
            if url not in self.wanted:continue
            ident=video_id(url);self.aliases[url]=ident
            row=self.cache.get(ident,{})
            if row.get('date') or time.time()-row.get('checked',0)<600:continue
            if url not in self.requested:self.requested.add(url);self.jobs.put(url)
        if self.wanted and not self.started:
            self.started=True
            for _ in range(2):threading.Thread(target=self.worker,daemon=True).start()

    def poll(self):
        dirty=False
        while not self.results.empty():
            url,row=self.results.get_nowait();self.requested.discard(url)
            if row is not None:self.cache[video_id(url)]=row;dirty=True
        if dirty:timing.media.atomic_write(timing.state()/'video-dates.json',json.dumps(self.cache))
        text=''.join(url+'\t'+display_date(self.cache[ident].get('date'))+'\n' for url,ident in self.aliases.items() if ident in self.cache)
        if text!=self.previous:timing.media.atomic_write(self.path,text);self.previous=text
