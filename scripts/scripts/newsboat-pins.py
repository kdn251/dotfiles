#!/usr/bin/env python3
"""Persistent cross-list pins; timestamps preserve original pin order on undo."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import newsboat_media as media


def key(url):
    identity = media.identity(url)
    return ':'.join(identity) if identity else url


def paths():
    state=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'newsboat'
    return state/'pins.json', Path(os.environ.get('NEWSBOAT_PINS_FILE',state/'pins.tsv'))


def change(action, url='', previous=0):
    source, target=paths()
    source.parent.mkdir(parents=True,exist_ok=True)
    with source.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try: pins=json.loads(source.read_text())
        except FileNotFoundError:pins={}
        if action!='refresh':
            if not url or any(c in url for c in '\n\r\t'):raise ValueError('Invalid pin URL')
            ident=key(url)
            if action=='save' and ident not in pins:
                pins[ident]=dict(url=url,order=max(time.time_ns(),max((v['order'] for v in pins.values()),default=0)+1))
            elif action=='remove' or (action=='restore' and not previous):pins.pop(ident,None)
            elif action=='restore':pins[ident]=dict(url=url,order=int(previous))
            elif action!='save':raise ValueError('Unknown pin action')
        media.atomic_write(source,json.dumps(pins,ensure_ascii=False))
        aliases={entry['url']:entry['order'] for entry in pins.values()}
        for ident,entry in pins.items():
            if ident.startswith('youtube:'):
                video=ident.split(':',1)[1]
                aliases['https://www.youtube.com/watch?v='+video]=entry['order']
                aliases['https://youtu.be/'+video]=entry['order']
        cache=Path(os.environ.get('NEWSBOAT_CACHE',Path.home()/'.newsboat/cache.db'))
        try:
            with closing(sqlite3.connect(cache.as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
                for (url,) in db.execute('SELECT DISTINCT url FROM rss_item'):
                    if key(url) in pins:aliases[url]=pins[key(url)]['order']
        except sqlite3.Error:pass
        media.atomic_write(target,''.join(f'{url}\t{order}\n' for url,order in sorted(aliases.items(),key=lambda row:(row[1],row[0])) if not any(c in url for c in '\n\r\t')))


if __name__=='__main__':
    change(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else '',int(sys.argv[3]) if len(sys.argv)>3 else 0)
