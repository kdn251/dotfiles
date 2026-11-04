"""Conservative, channel-scoped episode groups stored as local playlists."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from urllib.parse import quote, parse_qs, urlparse

PREFIX='series_'

def episode(title):
    # Introductory video-specific text commonly precedes a vertical bar.
    match=re.search(r'(?i)\b(?:part|episode|ep\.?)\s*#?\s*(\d+)\b',title)
    if not match:return None
    name=title[:match.start()].rsplit('|',1)[-1].strip(' -–—:|')
    if len(name)<3:return None
    key=re.sub(r'[^\w]+',' ',name.casefold()).strip()
    return name,key,int(match[1])

def series_id(url):
    ident=parse_qs(urlparse(url).query).get('list',[''])[0]
    return ident if re.fullmatch(r'series_[a-f0-9]{24}',ident) else None

def descriptor(lib, ident):
    return lib.LIBRARY/'series'/(ident+'.json')

def title_for(lib,url):
    row=lib.saved_item(url)
    if row and row.get('title'):return row['title']
    try:
        with closing(sqlite3.connect(lib.CACHE.as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
            row=db.execute('SELECT title FROM rss_item WHERE url=?',(url,)).fetchone()
            if row:return row[0]
    except sqlite3.Error:pass
    return lib.extract(url).get('title','')

def metadata(lib, url, force=False):
    ident=series_id(url)
    try:data=json.loads(descriptor(lib,ident).read_text())
    except (OSError,ValueError):raise ValueError('This detected series is no longer available')
    if force or not data.get('entries'):
        try:
            found=lib.extract(data['channel_url']+'/search?query='+quote(data['series_name']),force)
            entries={}
            for entry in found.get('entries') or []:
                if not entry:continue
                parsed=episode(entry.get('title',''))
                if not parsed or parsed[1]!=data['series_key']:continue
                cid=entry.get('channel_id')
                if cid and cid!=data['channel_id']:continue
                if not re.fullmatch(r'[A-Za-z0-9_-]{11}',entry.get('id','')):continue
                entries[entry['id']]=dict(entry,channel_id=data['channel_id'],
                    channel=data['channel'],episode=parsed[2])
            # Preserve already discovered episodes if YouTube search is incomplete.
            for entry in data.get('entries',[]):
                entries.setdefault(entry['id'],entry)
            data['entries']=sorted(entries.values(),key=lambda e:(e['episode'],e.get('timestamp') or 0,e['id']))
            lib.atomic_write(descriptor(lib,ident),json.dumps(data))
        except (OSError,ValueError,TimeoutError):
            if not data.get('entries'):raise
    return data

def detect(lib,url,channel,channel_data,force=False):
    try:url=lib.video_url(url)
    except ValueError:return None
    parsed=episode(title_for(lib,url))
    if not parsed:return None
    name,key,number=parsed
    cid=channel_data.get('channel_id') or channel.rsplit('/',1)[-1]
    ident=PREFIX+hashlib.sha256((cid+'|'+key).encode()).hexdigest()[:24]
    link='newsboat-series://playlist?list='+ident
    path=descriptor(lib,ident)
    if not path.exists():
        data=dict(id=ident,title=name+' · Detected series',series_name=name,series_key=key,
                  channel=channel_data.get('channel') or channel_data.get('uploader') or '',
                  channel_id=cid,channel_url=channel,entries=[])
        lib.atomic_write(path,json.dumps(data))
    data=metadata(lib,link,force=True)
    if len(data['entries'])<2:return None
    first=data['entries'][0]['id']
    lib.atomic_write(lib.LIBRARY/'playlist-covers'/(ident+'.json'),
                     json.dumps({'url':f'https://i.ytimg.com/vi/{first}/maxresdefault.jpg','channel_id':cid}))
    return dict(url=link,title=data['title'],source=data['channel'],channel_id=cid)
