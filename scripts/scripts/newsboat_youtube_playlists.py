"""YouTube playlist metadata and selected-video imports shared with Starred."""
from contextlib import closing
from datetime import datetime
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET
from newsboat_media import atomic_write, identity
from newsboat_miniflux import Client

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
LIBRARY = STATE/'youtube-playlists'
CACHE = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))


def video_url(url):
    key = identity(url)
    if not key or key[0] != 'youtube':
        raise ValueError('Select a YouTube video to browse its creator’s playlists')
    return 'https://www.youtube.com/watch?v='+key[1]


def playlist_url(url):
    p = urlparse(url)
    value = parse_qs(p.query).get('list', [''])[0]
    if p.hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com'} or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid YouTube playlist')
    return 'https://www.youtube.com/playlist?list='+value


def item_path(url):
    return LIBRARY/'videos'/(identity(video_url(url))[1]+'.json')


def saved_item(url):
    try:
        return json.loads(item_path(url).read_text())
    except (OSError, ValueError):
        return None


def remember(row):
    path = item_path(row['url'])
    previous = saved_item(row['url']) or {}
    previous.update({k:v for k,v in row.items() if v is not None and v != ''})
    atomic_write(path, json.dumps(previous))


def extract(url, force=False):
    path = LIBRARY/'metadata'/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    cached = None
    try:
        cached = json.loads(path.read_text())
        if not force and time.time()-path.stat().st_mtime < 3600:
            return cached
    except (OSError, ValueError):
        pass
    executable = Path.home()/'.local/bin/yt-dlp'
    command = [str(executable) if executable.exists() else 'yt-dlp', '--ignore-config',
               '--flat-playlist', '--skip-download', '--dump-single-json',
               '--socket-timeout', '10', '--retries', '1', '--extractor-retries', '1', '--', url]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        if cached is not None:
            return cached
        raise
    if result.returncode:
        if cached is not None:
            return cached
        raise ValueError('YouTube could not load this list. Try again shortly. '+result.stderr.strip()[-250:])
    data = json.loads(result.stdout)
    atomic_write(path, json.dumps(data))
    return data


def channel_url(url):
    """Recognize channel pages and subscription RSS without a network lookup."""
    parsed = urlparse(url)
    if parsed.hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
        return None
    path = parsed.path.rstrip('/')
    if path == '/feeds/videos.xml':
        cid = parse_qs(parsed.query).get('channel_id', [''])[0]
        if re.fullmatch(r'UC[A-Za-z0-9_-]{22}', cid):
            return 'https://www.youtube.com/channel/'+cid
    match = re.fullmatch(r'(/channel/UC[A-Za-z0-9_-]{22}|/@[^/]+|/(?:c|user)/[^/]+)(?:/(?:featured|videos|streams|shorts|playlists))?', path)
    if match:
        return 'https://www.youtube.com'+match[1]
    return None


def browse_url(url):
    # Miniflux-backed feed rows pass their numeric subscription ID.
    if re.fullmatch(r'[0-9]+', url):
        return url
    if playlist := browse_playlist_url(url):
        return playlist
    return channel_url(url) or video_url(url)


def browse_playlist_url(url):
    """Normalize playlist rows from YouTube and the local Playthroughs list."""
    if url.startswith('newsboat-playthroughs://'):
        ident = url.split('://', 1)[1]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', ident):
            raise ValueError('Invalid local playlist')
        return 'https://www.youtube.com/playlist?list='+ident
    parsed = urlparse(url)
    if parsed.path == '/playlist' and parsed.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
        return playlist_url(url)
    return None


def channel_for(url):
    if re.fullmatch(r'[0-9]+', url):
        feed = Client().request('feeds/'+url)
        channel = channel_url(feed.get('feed_url', '')) or channel_url(feed.get('site_url', ''))
        if not channel:
            raise ValueError('Select a YouTube feed to browse its creator’s playlists')
        return channel
    if channel := channel_url(url):
        return channel
    if playlist := browse_playlist_url(url):
        data = extract(playlist)
        # Use the playlist owner, not the uploader of its first video: curated
        # playlists can contain videos from several different channels.
        for key in ('channel_url', 'uploader_url'):
            if channel := channel_url(data.get(key) or ''):
                return channel
        cid = data.get('channel_id') or data.get('uploader_id') or ''
        if re.fullmatch(r'UC[A-Za-z0-9_-]{22}', cid):
            return 'https://www.youtube.com/channel/'+cid
        raise ValueError('Could not determine this playlist’s YouTube channel')
    url = video_url(url)
    row = saved_item(url)
    if row and row.get('channel_id'):
        return 'https://www.youtube.com/channel/'+row['channel_id']
    # A subscribed feed gives us the channel without extracting a playable video.
    try:
        with closing(sqlite3.connect(CACHE.as_uri()+'?mode=ro', uri=True, timeout=1)) as db:
            ids = {str(r[0]) for r in db.execute('SELECT feedurl FROM rss_item WHERE url=?', (url,))}
        for feed in Client().request('feeds'):
            if str(feed['id']) in ids:
                cid = parse_qs(urlparse(feed['feed_url']).query).get('channel_id',[''])[0]
                if re.fullmatch(r'UC[A-Za-z0-9_-]{22}', cid):
                    return 'https://www.youtube.com/channel/'+cid
    except (OSError, ValueError, sqlite3.Error):
        pass
    data = extract(url)
    cid = data.get('channel_id')
    if not cid or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', cid):
        raise ValueError('Could not determine this video’s YouTube channel')
    return 'https://www.youtube.com/channel/'+cid


def playlists(url, force=False):
    channel = channel_for(url)
    data = extract(channel+'/playlists', force)
    rows = []
    for entry in data.get('entries') or []:
        if not entry:
            continue
        try:
            link = playlist_url(entry.get('url',''))
        except ValueError:
            continue
        thumbnails = [t for t in (entry.get('thumbnails') or []) if t and t.get('url')]
        cover = entry.get('thumbnail') or (thumbnails[-1]['url'] if thumbnails else None)
        if cover and urlparse(cover).scheme in {'http', 'https'}:
            ident = parse_qs(urlparse(link).query)['list'][0]
            target = LIBRARY/'playlist-covers'/(ident+'.json')
            content = json.dumps({'url':cover,'channel_id':data.get('channel_id')})
            if not target.exists() or target.read_text() != content:
                atomic_write(target,content)
                (LIBRARY/'thumbnails'/('playlist:'+ident+'.png')).unlink(missing_ok=True)
        rows.append(dict(url=link, title=entry.get('title') or 'Untitled playlist',
                         source=data.get('channel') or '', channel_id=data.get('channel_id')))
    return data.get('channel') or data.get('title','Creator'), rows


def videos(url, force=False):
    data = extract(playlist_url(url), force)
    rows = []
    for position, entry in enumerate(data.get('entries') or [], 1):
        if not entry or not re.fullmatch(r'[A-Za-z0-9_-]{11}', entry.get('id','')):
            continue
        if entry.get('availability') in {'private', 'needs_auth', 'subscriber_only'} or entry.get('title') in {'[Private video]', '[Deleted video]'}:
            continue
        row = dict(url='https://www.youtube.com/watch?v='+entry['id'],
                   title=entry.get('title') or entry['id'],
                   source=entry.get('channel') or entry.get('uploader') or data.get('channel') or '',
                   channel_id=entry.get('channel_id') or data.get('channel_id'),
                   published=entry.get('timestamp'), duration=entry.get('duration'), position=position)
        remember(row)
        rows.append(row)
    return data.get('title','Playlist'), rows


def cache_entry(entry):
    """Put an explicitly selected remote entry in Newsboat's main cache."""
    if not CACHE.exists():
        return
    feed = entry['feed'];url = entry['url']
    try:
        stamp = int(datetime.fromisoformat(entry['published_at'].replace('Z','+00:00')).timestamp())
    except (KeyError, ValueError):
        stamp = int(time.time())
    with closing(sqlite3.connect(CACHE, timeout=3)) as db, db:
        if db.execute('SELECT 1 FROM rss_item WHERE guid=?', (str(entry['id']),)).fetchone():
            return
        db.execute('INSERT OR IGNORE INTO rss_feed(rssurl,url,title) VALUES (?,?,?)',
                   (str(feed['id']), feed.get('site_url',''), feed['title']))
        db.execute('INSERT INTO rss_item(guid,title,author,url,feedurl,pubDate,content,unread) VALUES (?,?,?,?,?,?,?,?)',
                   (str(entry['id']),entry['title'],entry.get('author',''),url,str(feed['id']),stamp,
                    entry.get('content',''),int(entry.get('status')=='unread')))
    revisions = LIBRARY/'imports.tsv'
    try:lines = revisions.read_text().splitlines()
    except OSError:lines = []
    lines.append(str(feed['id'])+'\t'+str(entry['id']))
    atomic_write(revisions, '\n'.join(lines[-500:])+'\n')
    # The download query may already exist before the import finishes. Wake
    # Newsboat's local-query watcher even when its expression did not change.
    urls = Path(os.environ.get('NEWSBOAT_URLS_FILE', Path.home()/'.newsboat/urls'))
    if urls.exists():
        os.utime(urls, None)


def ensure_entry(url, client=None):
    """Import only an acted-on video; browsing never fills New with a playlist."""
    row = saved_item(url)
    if not row:
        return None
    client = client or Client()
    LIBRARY.mkdir(parents=True, exist_ok=True)
    with (LIBRARY/'import.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        row = saved_item(url)
        if row.get('entry_id'):
            from urllib.error import HTTPError
            try:
                entry = client.request('entries/'+str(row['entry_id']))
                if entry['url'] == row['url']:
                    cache_entry(entry)
                    return entry['id']
            except HTTPError as error:
                if error.code != 404:raise
        feeds = client.request('feeds')
        cid = row.get('channel_id','')
        if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', cid):
            cid = channel_for(url).rsplit('/',1)[-1]
        feed_url = 'https://www.youtube.com/feeds/videos.xml?channel_id='+cid
        feed = next((f for f in feeds if parse_qs(urlparse(f['feed_url']).query).get('channel_id') == [cid]), None)
        if not feed:
            # Keep unfamiliar creators as manual-only sources, without subscribing
            # the user to every future upload just because they saved one episode.
            root=ET.Element('opml',version='2.0');body=ET.SubElement(root,'body')
            group=ET.SubElement(body,'outline',text='YouTube',title='YouTube')
            ET.SubElement(group,'outline',type='rss',text=row['source'] or 'YouTube',
                          title=row['source'] or 'YouTube',xmlUrl=feed_url,
                          htmlUrl='https://www.youtube.com/channel/'+cid,disabled='true')
            import urllib.request
            request=urllib.request.Request(client.base+'/v1/import',data=ET.tostring(root),
                headers={'Authorization':client.auth,'Content-Type':'application/xml'},method='POST')
            with urllib.request.urlopen(request,timeout=15):pass
            feed=next(f for f in client.request('feeds') if f['feed_url']==feed_url)
            client.request('feeds/'+str(feed['id']),{'disabled':True},method='PUT')
        # Check URL aliases before importing, including episodes already in RSS.
        offset=0;found=None
        while True:
            batch=client.request(f"feeds/{feed['id']}/entries?limit=1000&offset={offset}")
            found=next((e for e in batch['entries'] if identity(e['url'])==identity(url)),None)
            offset+=len(batch['entries'])
            if found or offset>=batch['total'] or not batch['entries']:break
        if found:
            entry_id=found['id']
        else:
            payload=dict(url=row['url'], title=row['title'], author=row['source'],
                         content='<p>'+html.escape(row['title'])+'</p>',status='read',starred=False)
            if row.get('published'):payload['published_at']=int(row['published'])
            entry_id=client.request(f"feeds/{feed['id']}/entries/import",payload,method='POST')['id']
        remember(dict(row,entry_id=entry_id))
        entry=client.request('entries/'+str(entry_id));cache_entry(entry)
        return entry_id
