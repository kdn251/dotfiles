"""Finished local Twitch VODs shared with the Newsboat media library."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import newsboat_media as media


def entries():
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
    try:
        saved = {row['url']: row for row in json.loads((state/'vod-items.json').read_text())}
    except (OSError, ValueError, KeyError):
        saved = {}
    jobs = {job['url']: job for _, job in media.records()}
    rows = {}
    for key, path in media.candidates():
        if key[0] != 'twitch' or not path.is_relative_to(media.ROOT):continue
        try:
            stat = path.stat()
        except OSError:
            continue
        url = 'https://www.twitch.tv/videos/'+key[1]
        info = saved.get(url) or jobs.get(url) or {}
        stem = re.sub(r'(?: - |\s*\[)v?'+re.escape(key[1])+r'\]?$', '', path.stem)
        source, sep, title = stem.partition(' - ')
        row = dict(url=url, path=str(path), title=info.get('title') or (title if sep else stem),
                   source=info.get('source') or info.get('creator') or (source if sep else 'Twitch'),
                   saved=stat.st_mtime)
        if url not in rows or rows[url]['saved'] < row['saved']:rows[url]=row
    return sorted(rows.values(), key=lambda row:row['saved'], reverse=True)


def play(row):
    if not Path(row['path']).is_file():
        raise ValueError('This video is no longer on disk. Switch tabs to refresh.')
    subprocess.Popen([sys.executable, str(Path(__file__).with_name('newsboat-play-video.py')),
                      row['url'], row['title']], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def downloads():
    """Match Downloads: omit scheduled VODs, playthroughs and streaming cache."""
    from newsboat_playthroughs import member_keys
    playlist_keys = member_keys()
    jobs = {media.identity(job['url']): job for _, job in media.records()}
    rows = {}
    bases = {'youtube':'https://www.youtube.com/watch?v=',
             'twitch':'https://www.twitch.tv/videos/', 'twitch-clip':'https://clips.twitch.tv/'}
    for key, path in media.candidates():
        if (not path.is_relative_to(media.ROOT) or path.parent == media.ROOT/'twitch-vods'
                or key in playlist_keys or key[0] not in bases):continue
        try:stat = path.stat()
        except OSError:continue
        info = jobs.get(key, {})
        title = re.sub(r'\s*\[[^\]]+\]$', '', path.stem)
        row = dict(url=info.get('url') or bases[key[0]]+key[1], path=str(path),
                   title=info.get('title') or title, source=info.get('creator') or key[0].title(),
                   icon=info.get('icon') or '', saved=stat.st_mtime)
        if key not in rows or rows[key]['saved'] < row['saved']:rows[key]=row
    return sorted(rows.values(), key=lambda row:row['saved'], reverse=True)
