#!/usr/bin/env python3
"""A persistent local collection for things saved for favorites."""
from contextlib import closing
from email.utils import formatdate
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

SCRIPTS = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
CACHE = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))
URLS = Path(os.environ.get('NEWSBOAT_URLS_FILE', Path.home()/'.newsboat/urls'))


def database():
    STATE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STATE/'favorites.db', timeout=3)
    (STATE/'favorites.db').chmod(0o600)
    db.execute('CREATE TABLE IF NOT EXISTS items(url TEXT PRIMARY KEY,title TEXT,source TEXT,content TEXT,saved REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS removed(url TEXT PRIMARY KEY,title TEXT,source TEXT,content TEXT,saved REAL)')
    return db


def entries():
    with closing(database()) as db:
        return db.execute('SELECT url,title,source,content,saved FROM items ORDER BY saved DESC').fetchall()


def save(url):
    if urlparse(url).scheme not in {'http', 'https'}:
        return
    title, source, content = url, '', ''
    try:
        with closing(sqlite3.connect(CACHE.as_uri()+'?mode=ro', uri=True)) as cache:
            row = cache.execute('SELECT i.title,f.title,i.content FROM rss_item i LEFT JOIN rss_feed f ON f.rssurl=i.feedurl WHERE i.url=? ORDER BY i.id DESC LIMIT 1', (url,)).fetchone()
            if row: title, source, content = row
    except sqlite3.Error:
        pass
    # Commentary can outlive the main feed cache too.
    if title == url:
        try:
            with closing(sqlite3.connect((STATE/'commentary.db').as_uri()+'?mode=ro', uri=True)) as db:
                row = db.execute('SELECT title,source,content FROM items WHERE url=?', (url,)).fetchone()
                if row: title, source, content = row
        except sqlite3.Error:
            pass
    if title == url:
        try:
            for row in json.loads((STATE/'starred-items.json').read_text()):
                if row['url'] == url:
                    title, source, content = row['title'], row['feed']['title'], row.get('content','')
                    break
        except (OSError, ValueError): pass
    if not source:
        from newsboat_sources import article_sources
        source = article_sources(CACHE, STATE).get(url, '')
    with closing(database()) as db, db:
        db.execute('INSERT OR IGNORE INTO items VALUES (?,?,?,?,?)', (url,title,source or '',content or '',time.time()))
    rebuild()


def remove(url):
    with closing(database()) as db, db:
        db.execute('INSERT OR REPLACE INTO removed SELECT * FROM items WHERE url=?', (url,))
        db.execute('DELETE FROM removed WHERE rowid NOT IN (SELECT rowid FROM removed ORDER BY rowid DESC LIMIT 100)')
        db.execute('DELETE FROM items WHERE url=?', (url,))
    rebuild()


def restore(url, saved):
    if saved:
        with closing(database()) as db, db:
            db.execute('INSERT OR IGNORE INTO items SELECT * FROM removed WHERE url=?', (url,))
            exists = db.execute('SELECT 1 FROM items WHERE url=?', (url,)).fetchone()
        if not exists:
            save(url)
            return
        rebuild()
    else:
        remove(url)


def rebuild():
    from newsboat_media import atomic_write, library_lock
    with library_lock():
        rows = entries()
        atomic_write(STATE/'starred-urls.txt.favorites.count', str(len(rows))+'\n')
        atomic_write(STATE/'starred-urls.txt.favorites', ''.join(row[0]+'\n' for row in rows
                     if not any(char in row[0] for char in '\r\n')))
        if not URLS.exists(): return
        lines = [line for line in URLS.read_text().splitlines() if not line.startswith(('"query: Favorites:', '"query:❤ Favorites:', '"query:💖 Favorites:', '"query:❤️ Favorites:'))]
        expression = ' or '.join('link = '+json.dumps(row[0]) for row in rows) or 'link = "newsboat-favorites://empty"'
        query = json.dumps('query: Favorites:'+expression, ensure_ascii=False)
        index = next((i for i,line in enumerate(lines) if line.startswith('"query:🌎 All:')),len(lines))
        lines.insert(index,query)
        text = '\n'.join(lines)+'\n'
        if text != URLS.read_text(): atomic_write(URLS,text)


def prepare_view(directory):
    spec=importlib.util.spec_from_file_location('history',SCRIPTS/'newsboat-history.py')
    history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)
    command,config=history.prepare_view(directory)
    rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
    ET.SubElement(channel,'title').text=' Favorites'
    ET.SubElement(channel,'link').text='https://localhost/favorites'
    ET.SubElement(channel,'description').text='Saved for the long term. F removes the selected item.'
    from newsboat_sources import article_sources, source_label
    sources = article_sources(CACHE, STATE)
    rows = entries()
    for url,title,source,content,saved in rows:
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text=title
        ET.SubElement(item,'author').text=source_label(url, source or sources.get(url, ''))
        ET.SubElement(item,'link').text=url
        ET.SubElement(item,'guid',isPermaLink='false').text=hashlib.sha256(url.encode()).hexdigest()
        ET.SubElement(item,'description').text=content
        ET.SubElement(item,'pubDate').text=formatdate(saved,usegmt=True)
    if not rows:
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text='No favorites saved — use f on an article to add it'
        ET.SubElement(item,'guid',isPermaLink='false').text='empty-favorites'
    ET.ElementTree(rss).write(Path(directory)/'history.xml',encoding='utf-8',xml_declaration=True)
    lines=[line for line in config.read_text().splitlines() if not line.startswith(('bind F ', 'macro F ', 'macro C ', 'article-sort-order '))]
    lines=[line.replace('toggle-article-read "read"','toggle-article-read "read" "stay"') if line.startswith(('bind o ','bind O ','macro v ','macro a ')) else line for line in lines]
    # Keep the original source visible in this list and its search results.
    lines += ['articlelist-format " %f  %D  %-9p %-20a │ %t"',
              'article-sort-order date-desc',
              'bind F articlelist undo-checkpoint favorites ; set browser "python3 ~/scripts/newsboat-favorites.py remove %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" ; delete-article ; purge-deleted -- "Remove from Favorites"',
              'bind F article,searchresultslist undo-checkpoint favorites ; set browser "python3 ~/scripts/newsboat-favorites.py remove %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" -- "Remove from Favorites"']
    config.write_text('\n'.join(lines)+'\n')
    return command,config


def show():
    with tempfile.TemporaryDirectory(prefix='newsboat-favorites-') as directory:
        command,config=prepare_view(directory)
        subprocess.run(command+['-x','reload'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        with config.open('a') as out:out.write('run-on-startup open\n')
        env=dict(os.environ)
        # These rows use local IDs, not Miniflux entry IDs.
        env.pop('NEWSBOAT_UNDO_HELPER',None)
        return subprocess.call(command,env=env)


if __name__ == '__main__':
    action=sys.argv[1]
    if action=='save':save(sys.argv[2])
    elif action=='remove':remove(sys.argv[2])
    elif action=='restore':restore(sys.argv[2],sys.argv[3]=='saved')
    elif action=='rebuild':rebuild()
    elif action=='show':sys.exit(show())
