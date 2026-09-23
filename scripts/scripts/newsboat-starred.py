#!/usr/bin/env python3
"""Display and change Miniflux stars directly; no separate saved-item database."""
from contextlib import closing
from email.utils import formatdate
import importlib.util
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from urllib.error import HTTPError

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from newsboat_miniflux import Client
URLS = Path(os.environ.get('NEWSBOAT_URLS_FILE', Path.home()/'.newsboat/urls'))
STARRED_STATUS = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/starred-urls.txt'
CACHE = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))


def entries(client=None):
    return (client or Client()).starred()


def rebuild_query(rows):
    # This is a disposable display index, never a second saved-item collection.
    from newsboat_media import atomic_write
    STARRED_STATUS.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(STARRED_STATUS.with_name('starred-items.json'), json.dumps(rows))
    atomic_write(Path(str(STARRED_STATUS)+'.count'), str(len(rows))+'\n')
    content = ''.join(url+'\n' for url in sorted({row['url'] for row in rows}) if not any(c in url for c in '\r\n'))
    if not STARRED_STATUS.exists() or STARRED_STATUS.read_text() != content:
        STARRED_STATUS.parent.mkdir(parents=True,exist_ok=True)
        atomic_write(STARRED_STATUS,content)
    if not URLS.exists():
        return
    current = URLS.read_text()
    lines = current.splitlines()
    index = next((i for i,line in enumerate(lines) if line.startswith(('"query:⭐ Starred:', '"query:📚 Shelf:'))), None)
    if index is None:
        return
    expression = ' or '.join('link = '+json.dumps(row['url']) for row in rows)
    expression = expression or 'link = "newsboat-starred://empty"'
    lines[index] = json.dumps('query:⭐ Starred:(' + expression + ') and feedtitle !~ "Starred"',ensure_ascii=False)
    content = '\n'.join(lines)+'\n'
    if content != current:
        target = URLS.resolve()
        with tempfile.NamedTemporaryFile(mode='w',dir=target.parent,delete=False) as out:
            out.write(content)
            temporary=Path(out.name)
        temporary.chmod(target.stat().st_mode & 0o777)
        temporary.replace(target)


def resolve_ids(url, client):
    ids = {row['id'] for row in client.starred() if row['url'] == url}
    try:
        with closing(sqlite3.connect(CACHE.as_uri()+'?mode=ro',uri=True,timeout=3)) as db:
            candidates = {int(row[0]) for row in db.execute('SELECT guid FROM rss_item WHERE url=?',(url,)) if str(row[0]).isdigit()}
        for entry_id in candidates - ids:
            try:
                item = client.request(f'entries/{entry_id}')
                if item['url'] == url:
                    ids.add(entry_id)
            except HTTPError as error:
                if error.code != 404:
                    raise
    except sqlite3.Error:
        pass
    return ids


def set_star(url, desired, client=None, mark_read=False):
    client = client or Client()
    ids = resolve_ids(url, client)
    if not ids and desired:
        raise ValueError('This item is no longer available in Miniflux')
    if ids:
        client.request('entries',{'entry_ids':sorted(ids),'starred':desired},method='PUT')
        if mark_read:
            client.request('entries',{'entry_ids':sorted(ids),'status':'read'},method='PUT')
    rebuild_query(client.starred())



def enqueue_star(url, desired, restore_unread=None):
    """Hand the request to a detached worker; the keyboard never waits on HTTP."""
    from newsboat_media import atomic_write
    queue = STARRED_STATUS.parent/'star-actions'
    queue.mkdir(parents=True, exist_ok=True)
    job = queue/f'{time.time_ns():020d}-{os.getpid()}.json'
    atomic_write(job, json.dumps({'url': url, 'desired': desired, 'cache': str(CACHE), 'restore_unread': restore_unread}))
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'work'],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        job.unlink(missing_ok=True)
        raise
    if desired is False and restore_unread is None and os.environ.get('NEWSBOAT_STARRED_REMOVALS'):
        markers = Path(os.environ['NEWSBOAT_STARRED_REMOVALS'])
        if markers.is_dir():
            atomic_write(markers/hashlib.sha256(url.encode()).hexdigest(), url)


def drain_star_actions():
    global CACHE
    queue = STARRED_STATUS.parent/'star-actions'
    queue.mkdir(parents=True, exist_ok=True)
    # Serialize rapid s/S requests so the final state follows keypress order.
    with (queue/'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        while jobs := sorted(queue.glob('*.json')):
            for job in jobs:
                try:
                    action = json.loads(job.read_text())
                    CACHE = Path(action['cache'])
                    if action.get('restore_unread') is None:
                        set_star(action['url'], action['desired'], mark_read=bool(action['desired']))
                    else:
                        client = Client()
                        ids = resolve_ids(action['url'], client)
                        if not ids:
                            raise ValueError('Item no longer available in Miniflux')
                        if action['desired'] is not None:
                            client.request('entries', {'entry_ids': sorted(ids), 'starred': action['desired']}, method='PUT')
                        client.request('entries', {'entry_ids': sorted(ids),
                            'status': 'unread' if action['restore_unread'] else 'read'}, method='PUT')
                        with closing(sqlite3.connect(CACHE, timeout=3)) as db, db:
                            db.executemany('UPDATE rss_item SET unread=? WHERE guid=?',
                                [(int(action['restore_unread']), str(i)) for i in ids])
                        rebuild_query(client.starred())
                except Exception:
                    subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '5000',
                                    'Star change failed',
                                    'Could not update Miniflux. Reopen Starred after syncing and try again.'], check=False)
                finally:
                    job.unlink(missing_ok=True)


def write_feed(directory, rows):
    rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
    for key,value in [('title','⭐ Starred'),('link','https://localhost/starred'),('description','Your Miniflux stars. Press S to unstar an item.')]:
        ET.SubElement(channel,key).text=value
    for index,row in enumerate(rows):
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text=row['title']+' — '+row['feed']['title']
        ET.SubElement(item,'link').text=row['url']
        ET.SubElement(item,'guid',isPermaLink='false').text=str(row['id'])
        ET.SubElement(item,'description').text=row.get('content','')
        ET.SubElement(item,'pubDate').text=formatdate(time.time()-index,usegmt=True)
    if not rows:
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text='No starred items — press q to return, then s to star an item'
        ET.SubElement(item,'guid',isPermaLink='false').text='empty-starred'
    ET.ElementTree(rss).write(Path(directory)/'history.xml',encoding='utf-8',xml_declaration=True)


def prepare_view(directory, rows):
    spec=importlib.util.spec_from_file_location('newsboat_history_view',SCRIPTS/'newsboat-history.py')
    history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)
    command,config=history.prepare_view(directory)
    write_feed(directory,rows)
    lines=[line for line in config.read_text().splitlines() if not line.startswith(('macro C ','bind S ','bind H ','show-read-articles ','article-sort-order '))]
    # Opening a saved item leaves it selected so S can remove it when finished.
    # Keep advancement for explicit read/star/download actions unchanged.
    lines = [line.replace('toggle-article-read "read"', 'toggle-article-read "read" "stay"')
             if line.startswith(('bind o ', 'bind O ', 'macro v ', 'macro a ')) else
             line.replace('toggle-article-read ;', 'toggle-article-read "toggle" "stay" ;')
             if line.startswith('macro r ') else line for line in lines]
    # Searches expose the synthetic feed title; the real source is already
    # included in each item's title, so omit the redundant feed column.
    lines += ['articlelist-format " %f  %D  %-9p %t"',
              'show-read-articles yes','article-sort-order date-desc',
              'bind S articlelist undo-checkpoint unstar ; set browser "python3 ~/scripts/newsboat-starred.py remove %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" ; delete-article ; purge-deleted -- "Unstar item"',
              'bind S article,searchresultslist undo-checkpoint unstar ; set browser "python3 ~/scripts/newsboat-starred.py remove %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" -- "Unstar item"',
              'macro C clear-filter ; delete-all-articles -- "Unstar all displayed items (asks for confirmation)"']
    if not os.environ.get('NEWSBOAT_UNDO_HELPER'):
        lines = [line.replace('undo-checkpoint unstar ; ', '') for line in lines]
    config.write_text('\n'.join(lines)+'\n')
    return command,config



def sync_read_status(directory, rows):
    # The generated RSS has no read-state field; restore Miniflux's state after
    # importing it, before opening the local view. Keep both states visible.
    with closing(sqlite3.connect(Path(directory)/'cache.db')) as db, db:
        db.executemany('UPDATE rss_item SET unread=? WHERE guid=?',
                       [(int(row.get('status') == 'unread'), str(row['id'])) for row in rows])


def view_entries():
    # Refreshed at session startup, by maintenance, and after each star change.
    # Keep opening the list independent of server latency when a snapshot exists.
    try:
        rows = json.loads(STARRED_STATUS.with_name('starred-items.json').read_text())
        if not isinstance(rows, list):
            raise ValueError('Invalid starred snapshot')
    except (OSError, ValueError):
        rows = entries()
        rebuild_query(rows)
    # A local read can happen after the snapshot (including s's mark-read step).
    try:
        with closing(sqlite3.connect(CACHE.as_uri()+'?mode=ro', uri=True, timeout=.1)) as db:
            read_ids = {str(row[0]) for row in db.execute('SELECT guid FROM rss_item WHERE unread=0')}
        for row in rows:
            if str(row['id']) in read_ids:
                row['status'] = 'read'
    except sqlite3.Error:
        pass
    return rows


def show():
    rows=view_entries()
    with tempfile.TemporaryDirectory(prefix='newsboat-starred-') as directory:
        command,config=prepare_view(directory,rows)
        subprocess.run(command+['-x','reload'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        sync_read_status(directory, rows)
        with config.open('a') as out:out.write('run-on-startup open\n')
        markers = Path(directory)/'managed-removals'
        markers.mkdir()
        process = subprocess.Popen(command, env=dict(os.environ, NEWSBOAT_STARRED_REMOVALS=str(markers)))
        finished = threading.Event()
        def wait_for_exit():
            process.wait()
            finished.set()
        waiter = threading.Thread(target=wait_for_exit, daemon=True)
        waiter.start()
        handled = set()
        visible_ids = {str(row['id']) for row in rows}
        while True:
            finished.wait(timeout=.2)
            # Only explicit deletion (C), never read status, removes stars.
            with closing(sqlite3.connect(Path(directory)/'cache.db')) as db:
                removed = {str(row[0]) for row in db.execute('SELECT guid FROM rss_item WHERE deleted=1')}
            handled.intersection_update(removed)
            # S already queued its own request. Only C's deletions need the
            # watcher; sending a second S request could race a subsequent undo.
            for marker in markers.iterdir():
                managed = {str(row['id']) for row in rows if row['url'] == marker.read_text()}
                if managed & removed:
                    handled.update(managed & removed)
                    marker.unlink(missing_ok=True)
            pending = (removed & visible_ids) - handled
            if pending:
                handled.update(pending)
                try:
                    client = Client()
                    client.request('entries', {'entry_ids': sorted(map(int,pending)), 'starred':False}, method='PUT')
                    rebuild_query(client.starred())
                except Exception:
                    subprocess.run(['notify-send','-a','Newsboat','-t','5000','Could not unstar items','Miniflux was unavailable. Reopen Starred to restore the list and try again.'])
            if process.poll() is not None:
                break


def main():
    try:
        action=sys.argv[1]
        if action in {'save','remove'}:
            enqueue_star(sys.argv[2],action=='save')
        elif action=='restore':
            enqueue_star(sys.argv[2], {'star':True, 'unstar':False, 'keep':None}[sys.argv[3]], sys.argv[4]=='unread')
        elif action=='work':drain_star_actions()
        elif action=='rebuild':rebuild_query(entries())
        elif action=='show':show()
        return 0
    except Exception as error:
        if isinstance(error, subprocess.CalledProcessError):
            message = 'Newsboat could not load the Starred view configuration.'
        else:
            message=str(error) if isinstance(error,ValueError) else 'Could not reach Miniflux. Please try again when connected.'
        if not os.environ.get('NEWSBOAT_QUIET_ERROR'):
            subprocess.run(['notify-send','-a','Newsboat','-t','5000','Starred unavailable',message])
        print(message,file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
