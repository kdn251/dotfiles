#!/usr/bin/env python3
"""Local, newest-first history of Newsboat browser and successful video opens."""
from contextlib import closing, contextmanager
from email.utils import formatdate
import hashlib
import tempfile
import xml.etree.ElementTree as ET
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlparse

SCRIPTS = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
CACHE = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))


@contextmanager
def database():
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE/'history.db'
    db = sqlite3.connect(path, timeout=3)
    os.chmod(path, 0o600)
    db.execute('CREATE TABLE IF NOT EXISTS history (url TEXT PRIMARY KEY, title TEXT, source TEXT, mode TEXT, opened REAL)')
    try:
        with db:
            yield db
    finally:
        db.close()


def record(url, mode):
    if mode not in {'browser', 'video'} or urlparse(url).scheme not in {'http', 'https'}:
        return
    title, source = url, urlparse(url).hostname or ''
    try:
        with closing(sqlite3.connect(CACHE.as_uri()+'?mode=ro', uri=True, timeout=1)) as cache:
            row = cache.execute('SELECT i.title, f.title FROM rss_item i LEFT JOIN rss_feed f ON i.feedurl=f.rssurl WHERE i.url=? ORDER BY i.pubDate DESC LIMIT 1', (url,)).fetchone()
            if row:
                title, source = row[0] or title, row[1] or source
    except sqlite3.Error:
        pass
    with database() as db:
        db.execute('INSERT INTO history VALUES (?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title, source=excluded.source, mode=excluded.mode, opened=excluded.opened',
                   (url, title, source, mode, time.time()))
        db.execute('DELETE FROM history WHERE url NOT IN (SELECT url FROM history ORDER BY opened DESC LIMIT 500)')


def entries():
    with database() as db:
        return db.execute('SELECT url,title,source,mode,opened FROM history ORDER BY opened DESC').fetchall()


def prepare_view(directory):
    directory = Path(directory)
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for name, value in [('title', 'History'), ('link', 'https://localhost/history'),
                        ('description', 'Recently opened items; newest first')]:
        ET.SubElement(channel, name).text = value
    rows = entries()
    for url, title, source, mode, stamp in rows:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = f'{title} — {source}'
        ET.SubElement(item, 'link').text = url
        ET.SubElement(item, 'guid', isPermaLink='false').text = hashlib.sha256(url.encode()).hexdigest()
        ET.SubElement(item, 'pubDate').text = formatdate(stamp, usegmt=True)
        ET.SubElement(item, 'description').text = f'Opened in {mode}. Source: {source}. Use o/O for Brave or ,v for video playback.'
    if not rows:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = 'No history yet — open a link with o/O or play a video with ,v'
        ET.SubElement(item, 'guid', isPermaLink='false').text = 'empty-history'
        ET.SubElement(item, 'description').text = 'Press q to return. Your recently opened items will appear here.'
    feed = directory/'history.xml'
    ET.ElementTree(rss).write(feed, encoding='utf-8', xml_declaration=True)
    urls = directory/'urls'
    urls.write_text(feed.as_uri() + '\n')
    # Reuse appearance and actions, without connecting this local view to Miniflux.
    source = Path.home()/'.newsboat/config'
    if not source.exists():
        source = SCRIPTS.parents[1]/'newsboat/.newsboat/config'
    allowed = {'color', 'highlight', 'highlight-article', 'articlelist-format',
               'articlelist-title-format', 'datetime-format', 'text-width',
               'browser', 'bind', 'bind-key', 'macro'}
    lines = [line for line in source.read_text().splitlines()
             if line.split() and line.split()[0] in allowed and not line.startswith('bind H ')]
    lines += ['show-read-feeds yes', 'show-read-articles yes', 'article-sort-order date-desc',
              'confirm-exit no', 'bind q articlelist hard-quit',
              'bind H articlelist hard-quit -- "Return from history"']
    config = directory/'config'
    config.write_text('\n'.join(lines) + '\n')
    command = ['newsboat', '-q', '-C', str(config), '-u', str(urls), '-c', str(directory/'cache.db')]
    return command, config


def show():
    with tempfile.TemporaryDirectory(prefix='newsboat-history-') as directory:
        command, config = prepare_view(directory)
        subprocess.run(command + ['-x', 'reload'], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
        with config.open('a') as output:
            output.write('run-on-startup open\n')
        subprocess.run(command, check=False)


if __name__ == '__main__':
    try:
        if sys.argv[1:2] == ['record']:
            record(sys.argv[2], sys.argv[3])
        elif sys.argv[1:2] == ['show']:
            show()
    except (OSError, sqlite3.Error):
        # History must never prevent the selected item from opening.
        pass
