#!/usr/bin/env python3
"""Search cached feeds and durable collections without contacting feed servers."""
from contextlib import closing
from datetime import datetime
from email.utils import formatdate
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from newsboat_loading import nested_view_environment
from newsboat_sources import feed_titles, source_label
from newsboat_media import library_identity

SCRIPTS = Path(__file__).resolve().parent
LABELS = ('New', 'Starred', 'Downloads', 'Favorites', 'Commentary', 'Playthroughs', 'VODs', 'Queue')


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def read_db(path, query):
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=.3)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(query)]
    except sqlite3.Error:
        return []


def stamp(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except (ValueError, TypeError, AttributeError):
            return 0


def search(query, cache, state):
    catalog = {}
    titles = feed_titles(state)
    def add(row, labels=()):
        url = row.get('url', '')
        if not url.startswith(('https://', 'http://')):
            return
        key = library_identity(url) or ('url', url.split('#')[0])
        target = catalog.setdefault(key, dict(url=url, title='', source='', content='', saved=0, published=0, guid='', unread=None, labels=set()))
        for field in ('title', 'source', 'content', 'guid'):
            if not target[field] and row.get(field):
                target[field] = str(row[field])
        if target['unread'] is None and 'unread' in row:
            target['unread'] = bool(row['unread'])
        target['saved'] = max(target['saved'], stamp(row.get('saved')))
        if not target['published']:
            target['published'] = stamp(row.get('published'))
        target['labels'].update(labels)
        if row.get('download_badge'):target['download_badge']=row['download_badge']
    for row in read_db(cache, '''SELECT i.guid,i.url,i.title,i.content,i.author,i.pubDate AS saved,i.pubDate AS published,i.unread,i.feedurl,
                f.title AS source FROM rss_item i LEFT JOIN rss_feed f ON f.rssurl=i.feedurl
                WHERE i.deleted=0 ORDER BY i.pubDate DESC,i.id DESC'''):
        row['source'] = titles.get(row['feedurl']) or row['source'] or row['author'] or ''
        # Synthetic collection names are membership, not creator names.
        synthetic = next((label for label in LABELS if row['source'] == label or row['source'].endswith(' '+label)), None) if row['feedurl'].startswith(('query:', 'file:')) else None
        if synthetic:
            row['source'] = row['author'] or ''
        add(row, (['New'] if row['unread'] and not synthetic else []) + ([synthetic] if synthetic else []))
    for row in read_json(state/'starred-items.json', []):
        add(dict(url=row.get('url',''), title=row.get('title',''), source=(row.get('feed') or {}).get('title',''),
                 content=row.get('content',''), saved=row.get('published_at'), published=row.get('published_at'), guid=row.get('id'), unread=row.get('status') == 'unread'), ['Starred'])
    for name in ('favorites', 'commentary'):
        for row in read_db(state/(name+'.db'), 'SELECT url,title,source,content,saved FROM items'):
            add(row, [name.title()])
    for path in (state/'downloads').glob('*.json'):
        row = read_json(path, {})
        if not isinstance(row, dict) or not row.get('url'):
            continue
        status = row.get('status')
        if status == 'done':
            if not any(Path(p).is_file() for p in row.get('files', [])):
                continue
            badge = '📥'
        elif status in {'failed', 'cancelled'}:
            badge = '✕'
        elif status in {'preparing', 'downloading', 'processing', 'retrying', 'waiting'}:
            badge = '…'
        else:
            # Deleted/unknown records are history, not current downloads.
            continue
        add(dict(row, source=row.get('creator',''), saved=row.get('updated',0),
                 download_badge=badge), ['Downloads'])
    for path in (state/'youtube-playlists/playthroughs').glob('*.json'):
        group = read_json(path, {})
        for row in group.get('rows', []):
            add(dict(row, source=row.get('source') or group.get('channel','')), ['Playthroughs'])
    for name, label in [('vod-items.json', 'VODs'), ('viewing-queue.json', 'Queue')]:
        for row in read_json(state/name, []):
            add(row, [label])
    words = query.casefold().split()
    result = []
    for row in catalog.values():
        text = html.unescape(re.sub('<[^>]+>', ' ', ' '.join(row[key] for key in ('title','source','content')))).casefold()
        if words and all(word in text for word in words):
            if 'Playthroughs' in row['labels'] or 'VODs' in row['labels']:
                row['labels'].discard('Downloads')
            row['labels'] = [label for label in LABELS if label in row['labels']] or ['Feeds']
            row['title'] = row['title'] or row['url']
            result.append(row)
    return sorted(result, key=lambda row: (-(row['published'] or row['saved']), row['title'].casefold()))


def prepare(directory, query, rows, source):
    directory = Path(directory)
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, value in [('title', 'Search everything'), ('link', 'https://localhost/search'), ('description', 'Local search across feeds and saved items')]:
        ET.SubElement(channel,key).text=value
    labels = []
    for row in rows:
        item = ET.SubElement(channel, 'item')
        values = dict(title=row['title'], link=row['url'], author=source_label(row['url'],row['source']),
                      guid=row['guid'] or 'global:'+hashlib.sha256(row['url'].encode()).hexdigest(),
                      description=row['content'], pubDate=formatdate(row.get('published') or row['saved'],usegmt=True))
        for key,value in values.items():
            ET.SubElement(item,key).text=value
        labels.append(row['url']+'\t'+', '.join(row['labels']))
    if not rows:
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text='No matches — q to return and try another search'
        ET.SubElement(item,'guid').text='global-search-empty'
    rss_path=directory/'results.xml'
    ET.ElementTree(rss).write(rss_path, encoding='utf-8',xml_declaration=True)
    (directory/'urls').write_text(rss_path.as_uri()+'\n')
    (directory/'labels').write_text('\n'.join(labels)+'\n')
    allowed={'color','highlight','highlight-article','datetime-format','text-width','browser','bind','bind-key','macro','scrolloff'}
    lines=[line for line in source.read_text().splitlines() if line.split() and line.split()[0] in allowed]
    title=' 🔎 Search: '+query.replace('%','%%')+' · '+str(len(rows))+' results'
    lines += ['urls-source local','auto-reload no','show-read-feeds yes','show-read-articles yes',
              'confirm-exit no','article-sort-order date-asc','articlelist-title-format '+json.dumps(title,ensure_ascii=False),
              'searchresult-title-format " 🔎 Filter search results: %s"',
              'articlelist-format "%4i %D %-9p %-20a │ %-26b │ %8v %t"',
              'bind q articlelist hard-quit -- "Back to homepage"']
    config=directory/'config';config.write_text('\n'.join(lines)+'\n')
    binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
    return [str(binary) if binary.exists() else 'newsboat','-q','-C',str(config),'-u',str(directory/'urls'),'-c',str(directory/'cache.db')],config


class ResultBadges:
    """Project live status onto the URLs retained by deduplicated search results."""
    def __init__(self, rows, state, directory, env):
        self.rows = rows
        self.directory = Path(directory)
        self.versions = {}
        self.stop = threading.Event()
        stars = Path(env.get('NEWSBOAT_STARRED_STATUS', state/'starred-urls.txt'))
        downloads = Path(env.get('NEWSBOAT_DOWNLOAD_STATUS', state/'download-status.tsv'))
        self.sources = {
            'stars': (stars, 'Starred', False),
            'stars.commentary': (Path(str(stars)+'.commentary'), 'Commentary', False),
            'stars.favorites': (Path(str(stars)+'.favorites'), 'Favorites', False),
            'downloads': (downloads, 'Downloads', True),
        }
        for suffix in ('.vods', '.watched', '.read', '.order'):
            self.sources['downloads'+suffix] = (Path(str(downloads)+suffix), None, True)
        self.refresh(initial=True)
        env['NEWSBOAT_STARRED_STATUS'] = str(self.directory/'stars')
        env['NEWSBOAT_DOWNLOAD_STATUS'] = str(self.directory/'downloads')
        for key, filename in [('NEWSBOAT_NOTES_STATUS','noted-urls.txt'),
                              ('NEWSBOAT_PINS_FILE','pins.tsv'),
                              ('NEWSBOAT_LAST_OPENED','last-opened'),
                              ('NEWSBOAT_QUEUE_STATUS','viewing-queue.tsv')]:
            env.setdefault(key, str(state/filename))
        self.worker = threading.Thread(target=self.watch, daemon=True)

    def refresh(self, initial=False):
        for name, (source, label, values) in self.sources.items():
            try:
                info=source.stat();version=(info.st_mtime_ns,info.st_size)
                if not initial and self.versions.get(name)==version:continue
                lines=source.read_text().splitlines()
            except OSError:
                version=None;lines=[]
                if not initial and name in self.versions and self.versions[name] is None:continue
            self.versions[name]=version
            entries={}
            for line in lines:
                url, _, value=line.partition('\t')
                key=library_identity(url)
                if key:entries[key]=value
            # Keep all statuses available to any other list opened from these results.
            output=list(lines)
            original_urls={line.split('\t',1)[0] for line in lines}
            for row in self.rows:
                if row['url'] in original_urls:continue
                key=library_identity(row['url'])
                if key in entries:
                    value=entries[key]
                elif initial and label and label in row['labels']:
                    value=row.get('download_badge','📥') if values else ''
                else:continue
                output.append(row['url']+('\t'+value if values else ''))
            target=self.directory/name
            text='\n'.join(output)+'\n'
            if not target.exists() or target.read_text()!=text:
                temporary=target.with_name(target.name+'.tmp')
                temporary.write_text(text);temporary.replace(target)

    def watch(self):
        while not self.stop.wait(.1):
            self.refresh()

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *args):
        self.stop.set();self.worker.join(timeout=1)


def show(query):
    state=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'newsboat'
    cache=Path(os.environ.get('NEWSBOAT_CACHE',Path.home()/'.newsboat/cache.db'))
    source=Path.home()/'.newsboat/config'
    if not source.exists():source=SCRIPTS.parents[1]/'newsboat/.newsboat/config'
    rows=search(query,cache,state)
    with tempfile.TemporaryDirectory(prefix='newsboat-global-search-') as directory:
        command,config=prepare(directory,query,rows,source)
        env=nested_view_environment(directory)
        for key in ('NEWSBOAT_LIVE_QUERIES','NEWSBOAT_NESTED_VIEWS','NEWSBOAT_GLOBAL_SEARCH_REQUEST','NEWSBOAT_SYNC_VIEW'):
            env.pop(key,None)
        env['NEWSBOAT_SEARCH_LABELS']=str(Path(directory)/'labels')
        subprocess.run(command+['-x','reload'],env=env,capture_output=True,check=True,timeout=15)
        with closing(sqlite3.connect(Path(directory)/'cache.db')) as db, db:
            db.executemany('UPDATE rss_item SET unread=? WHERE url=?',
                           [(int(bool(row.get('unread'))), row['url']) for row in rows])
        with config.open('a') as out:out.write('run-on-startup open\n')
        from newsboat_thumbnails import run
        with ResultBadges(rows,state,directory,env):
            return run(command,env)


if __name__=='__main__':
    raise SystemExit(show(sys.argv[1]))
