"""Resolve YouTube/Twitch row avatars from local metadata before network work."""
from contextlib import closing
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
from urllib.parse import urlparse, parse_qs

from newsboat_media import identity, atomic_write
from newsboat_youtube_playlists import LIBRARY, CACHE, saved_item

STATE = LIBRARY.parent
FEED_LOCK = threading.Lock()
FEEDS = None


def load(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def channel_id(url):
    parsed = urlparse(url)
    if parsed.hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
        return None
    candidate = parse_qs(parsed.query).get('channel_id', [''])[0]
    if parsed.path.startswith('/channel/'):
        candidate = parsed.path.split('/')[2]
    return candidate if re.fullmatch(r'UC[A-Za-z0-9_-]{22}', candidate) else None


def feeds():
    global FEEDS
    with FEED_LOCK:
        if FEEDS is not None:
            return FEEDS
        path = STATE/'avatar-feeds.json'
        FEEDS = load(path, [])
        if FEEDS and time.time()-path.stat().st_mtime < 3600:
            return FEEDS
        try:
            from newsboat_miniflux import Client
            # Store only public source metadata, never feed authentication fields.
            FEEDS = [{k: row.get(k) for k in ('id','title','feed_url','site_url')}
                     for row in Client().request('feeds')]
            atomic_write(path, json.dumps(FEEDS))
        except Exception:
            pass
        return FEEDS


def label(value):
    return value.removeprefix(' ').removeprefix(' ').strip().casefold()


@lru_cache(maxsize=256)
def profile(platform, creator):
    if platform == 'youtube':
        if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', creator):
            return None
        directory, helper = 'yt-channel-avatars', 'yt-channel-pic.sh'
    else:
        creator = creator.lower()
        if not re.fullmatch(r'[a-z0-9_]{1,50}', creator):
            return None
        directory, helper = 'twitch-profiles', 'twitch-profile-pic.sh'
    path = Path.home()/'.cache'/directory/(creator+'.png')
    if not path.is_file() or not path.stat().st_size:
        subprocess.run([str(Path(__file__).with_name(helper)), creator],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=True)
    return path.read_bytes()


def feed_creator(row):
    for field in ('feed_url','site_url'):
        cid = channel_id(row.get(field) or '')
        if cid:
            return 'youtube', cid
        parsed = urlparse(row.get(field) or '')
        if parsed.hostname in {'twitch.tv','www.twitch.tv'} and re.fullmatch(r'/[A-Za-z0-9_]+/?',parsed.path):
            return 'twitch',parsed.path.strip('/').lower()
    return None


@lru_cache(maxsize=1)
def download_creators():
    from newsboat_media import records
    result = {}
    allowed = {'yt-channel-avatars':'youtube', 'twitch-profiles':'twitch'}
    for _, job in records():
        icon = Path(job.get('icon') or '')
        platform = allowed.get(icon.parent.name)
        media_key = identity(job.get('url',''))
        if platform and media_key:
            result[media_key] = platform,icon.stem
    for row in load(STATE/'vod-items.json', []):
        media_key = identity(row.get('url',''))
        if media_key:
            result[media_key] = 'twitch',row.get('source','')
    return result


def resolve(request):
    url, author, feed_id = (request.split('\t') + ['', ''])[:3]
    parsed = urlparse(url)
    if parsed.scheme == 'newsboat-feed':
        feed_id = parsed.netloc
    if cid := channel_id(url):
        return 'youtube', cid
    local_playlist = parsed.scheme == 'newsboat-playthroughs'
    playlist = local_playlist or parsed.path == '/playlist' and parsed.hostname in {'youtube.com','www.youtube.com'}
    if playlist:
        ident = parsed.netloc if local_playlist else parse_qs(parsed.query).get('list',[''])[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]+',ident):
            return None
        # Browsed playlists record their actual owner alongside the cover.
        cover = load(LIBRARY/'playlist-covers'/(ident+'.json'), {})
        if cover.get('channel_id'):
            return 'youtube', cover['channel_id']
        for path in (LIBRARY/'metadata'/(hashlib.sha256(('https://www.youtube.com/playlist?list='+ident).encode()).hexdigest()+'.json'), LIBRARY/'playthroughs'/(ident+'.json')):
            data = load(path, {})
            if data.get('channel_id'):
                return 'youtube',data['channel_id']
            for row in data.get('rows',[]):
                if row.get('channel_id'):
                    return 'youtube',row['channel_id']
    media_key = identity(url)
    if media_key:
        if media_key[0] == 'youtube':
            row = saved_item(url) or {}
            if row.get('channel_id'):
                return 'youtube',row['channel_id']
        if creator := download_creators().get(media_key):
            return creator
    if parsed.hostname in {'twitch.tv','www.twitch.tv','m.twitch.tv'}:
        parts = parsed.path.strip('/').split('/')
        if len(parts)==1 or len(parts)==3 and parts[1]=='clip':
            if re.fullmatch(r'[A-Za-z0-9_]+',parts[0]):
                return 'twitch',parts[0].lower()
        # Generated VOD rows store the downloader's exact Twitch login.
        if author.startswith(' ') and re.fullmatch(r'[A-Za-z0-9_]+',author[2:].strip()):
            return 'twitch',author[2:].strip().lower()
    if not feed_id.isdigit() and media_key:
        try:
            with closing(sqlite3.connect(CACHE.as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
                row = db.execute('SELECT feedurl,author FROM rss_item WHERE url=? ORDER BY id DESC LIMIT 1',(url,)).fetchone()
                if row:
                    feed_id, source = row
                    author = author or source
        except sqlite3.Error:
            pass
    sources = feeds()
    for source in sources:
        if str(source['id'])==feed_id:
            if creator := feed_creator(source):
                return creator
    matches = {creator for source in sources if label(source.get('title') or '')==label(author)
               if (creator := feed_creator(source))}
    if len(matches)==1:
        return matches.pop()
    # Unsubscribed video/history rows may have no local creator metadata.
    if media_key or playlist:
        youtube = bool(playlist or media_key and media_key[0] == 'youtube')
        executable=Path.home()/'.local/bin/yt-dlp'
        result=subprocess.run([str(executable) if executable.exists() else 'yt-dlp',
            '--ignore-config','--flat-playlist','--playlist-end','1','--skip-download',
            '--socket-timeout','4','--retries','0','--extractor-retries','0',
            '--print','%(channel_id)s' if youtube else '%(uploader_id)s',
            '--',url],capture_output=True,text=True,timeout=12,check=True)
        creator = result.stdout.strip().splitlines()[-1]
        return ('youtube' if youtube else 'twitch'),creator
    return None


def fetch(request):
    if creator := resolve(request):
        return profile(*creator)
    return None
