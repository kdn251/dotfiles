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
        raise ValueError('This VOD is no longer on disk. Press Tab twice to refresh.')
    subprocess.Popen([sys.executable, str(Path(__file__).with_name('newsboat-play-video.py')),
                      row['url'], row['title']], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
