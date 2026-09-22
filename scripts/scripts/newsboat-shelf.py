#!/usr/bin/env python3
"""Persistent save-for-later list; consuming an item in Shelf removes it."""
from contextlib import closing, contextmanager
from email.utils import formatdate
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import shlex
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

SCRIPTS = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
URLS = Path(os.environ.get('NEWSBOAT_URLS_FILE', Path.home()/'.newsboat/urls'))
CACHE = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))


@contextmanager
def database():
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE/'shelf.db'
    with closing(sqlite3.connect(path, timeout=3)) as db:
        os.chmod(path, 0o600)
        db.execute('CREATE TABLE IF NOT EXISTS shelf(url TEXT PRIMARY KEY,title TEXT,source TEXT,content TEXT,saved REAL)')
        with db:
            yield db


def save(url):
    if urlparse(url).scheme not in {'http', 'https'}:
        return
    title, source, content = url, urlparse(url).hostname or '', ''
    try:
        with closing(sqlite3.connect(CACHE.as_uri()+'?mode=ro', uri=True, timeout=1)) as db:
            row = db.execute('SELECT i.title,f.title,i.content FROM rss_item i LEFT JOIN rss_feed f ON i.feedurl=f.rssurl WHERE i.url=? ORDER BY i.pubDate DESC LIMIT 1', (url,)).fetchone()
            if row:
                title, source, content = row[0] or title, row[1] or source, row[2] or ''
    except sqlite3.Error:
        pass
    with database() as db:
        db.execute('INSERT INTO shelf VALUES (?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET saved=excluded.saved',
                   (url, title, source, content, time.time()))

    rebuild_query()


def consume(url):
    with database() as db:
        db.execute('DELETE FROM shelf WHERE url=? AND saved<=?',
                   (url, float(os.environ.get('NEWSBOAT_SHELF_SNAPSHOT', time.time()))))

    rebuild_query()


def entries():
    with database() as db:
        return db.execute('SELECT url,title,source,content,saved FROM shelf ORDER BY saved ASC').fetchall()


def rebuild_query():
    # Native query counts now reflect the saved articles, instead of a dummy link.
    if not URLS.exists():
        return
    current = URLS.read_text()
    lines = current.splitlines()
    position = next((i for i, line in enumerate(lines)
                     if line.startswith('"query:📚 Shelf:')), None)
    if position is None:
        return
    expression = ' or '.join('link = ' + json.dumps(row[0]) for row in entries())
    expression = expression or 'link = "newsboat-shelf://navigation"'
    lines[position] = json.dumps('query:📚 Shelf:(' + expression + ') and feedtitle !~ "Starred"', ensure_ascii=False)
    content = '\n'.join(lines) + '\n'
    if content != current:
        # Follow the stow symlink, and replace only after the full file is written.
        target = URLS.resolve()
        with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as output:
            output.write(content)
            temporary = Path(output.name)
        os.chmod(temporary, target.stat().st_mode & 0o777)
        temporary.replace(target)


def prepare_view(directory):
    # Share the normal Newsboat appearance/actions used by the History view.
    spec = importlib.util.spec_from_file_location('newsboat_history_view', SCRIPTS/'newsboat-history.py')
    history = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(history)
    command, config = history.prepare_view(directory)
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, value in [('title', '📚 Shelf'), ('link', 'https://localhost/shelf'),
                       ('description', 'Saved for later. Opening an item removes it from Shelf.')]:
        ET.SubElement(channel, key).text = value
    rows = entries()
    for url, title, source, content, stamp in rows:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = f'{title} — {source}'
        ET.SubElement(item, 'link').text = url
        ET.SubElement(item, 'guid', isPermaLink='false').text = hashlib.sha256(url.encode()).hexdigest()
        ET.SubElement(item, 'pubDate').text = formatdate(stamp, usegmt=True)
        ET.SubElement(item, 'description').text = content or f'Saved from {source}. Open with o/O or play with ,v.'
    if not rows:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = 'Shelf is empty — press q to return, then s on an item to save it'
        ET.SubElement(item, 'guid', isPermaLink='false').text = 'empty-shelf'
    ET.ElementTree(rss).write(Path(directory)/'history.xml', encoding='utf-8', xml_declaration=True)
    lines = [line for line in config.read_text().splitlines()
             if not line.startswith(('bind C ', 'bind H ', 'bind S ', 'bind s ', 'show-read-articles '))]
    consume_action = ('set browser "python3 ' + shlex.quote(str(Path(__file__).resolve()))
                      + ' consume %u" ; open-in-browser-noninteractively ; '
                      + 'set browser "~/scripts/newsboat-brave-app.sh %u"')
    lines = [line.replace('; toggle-article-read "read"', '; ' + consume_action + ' ; toggle-article-read "read"')
             if line.startswith(('bind o ', 'bind O ', 'macro v ')) else line for line in lines]
    lines += ['show-read-articles no',
              'confirm-delete-all-articles yes',
              'bind C articlelist clear-filter ; delete-all-articles ; purge-deleted -- "Clear Shelf (asks for confirmation)"',
              'bind ENTER articlelist open ; ' + consume_action + ' -- "Read and remove from Shelf"',
              'bind S article ' + consume_action + ' -- "Remove item from Shelf"',
              'bind S articlelist ' + consume_action + ' ; delete-article ; purge-deleted -- "Remove item from Shelf"']
    config.write_text('\n'.join(lines)+'\n')
    return command, config


def sync_consumed(cache, saved_before):
    with closing(sqlite3.connect(Path(cache).as_uri()+'?mode=ro', uri=True, timeout=1)) as view:
        consumed = view.execute('SELECT url FROM rss_item WHERE unread=0 OR deleted=1').fetchall()
    if consumed:
        with database() as db:
            db.executemany('DELETE FROM shelf WHERE url=? AND saved<=?',
                           [(url, saved_before) for (url,) in consumed])

        rebuild_query()


def show():
    with tempfile.TemporaryDirectory(prefix='newsboat-shelf-') as directory:
        saved_before = time.time()
        command, config = prepare_view(directory)
        subprocess.run(command+['-x', 'reload'], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
        with config.open('a') as output:
            output.write('run-on-startup open\n')
        process = subprocess.Popen(command, env=dict(os.environ, NEWSBOAT_SHELF_SNAPSHOT=str(saved_before)))
        while True:
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
            sync_consumed(Path(directory)/'cache.db', saved_before)
            if process.poll() is not None:
                break


if __name__ == '__main__':
    if sys.argv[1:2] == ['save']:
        save(sys.argv[2])
        subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '2000', 'Saved to Shelf', 'Open Shelf from the main feed list.'])
    elif sys.argv[1:2] == ['remove']:
        consume(sys.argv[2])
        subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '2000', 'Removed from Shelf'])
    elif sys.argv[1:2] == ['consume']:
        consume(sys.argv[2])
    elif sys.argv[1:2] == ['rebuild']:
        rebuild_query()
    elif sys.argv[1:2] == ['show']:
        show()
