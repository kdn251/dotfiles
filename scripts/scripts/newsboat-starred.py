#!/usr/bin/env python3
"""Display and change Miniflux stars directly; no separate saved-item database."""
from contextlib import closing
from email.utils import formatdate
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
from urllib.error import HTTPError

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from newsboat_miniflux import Client
URLS = Path(os.environ.get('NEWSBOAT_URLS_FILE', Path.home()/'.newsboat/urls'))
CACHE = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))


def entries(client=None):
    return (client or Client()).starred()


def rebuild_query(rows):
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


def set_star(url, desired, client=None):
    client = client or Client()
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
    if not ids and desired:
        raise ValueError('This item is no longer available in Miniflux')
    if ids:
        client.request('entries',{'entry_ids':sorted(ids),'starred':desired},method='PUT')
    rebuild_query(client.starred())


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
    lines=[line for line in config.read_text().splitlines() if not line.startswith(('bind C ','bind S ','bind H ','show-read-articles ','article-sort-order '))]
    lines += ['show-read-articles yes','article-sort-order date-desc',
              'bind S articlelist set browser "python3 ~/scripts/newsboat-starred.py remove %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" ; delete-article ; purge-deleted -- "Unstar item"',
              'bind S article,searchresultslist set browser "python3 ~/scripts/newsboat-starred.py remove %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" -- "Unstar item"',
              'bind C articlelist clear-filter ; delete-all-articles -- "Unstar all displayed items (asks for confirmation)"']
    config.write_text('\n'.join(lines)+'\n')
    return command,config


def show():
    rows=entries()
    rebuild_query(rows)
    with tempfile.TemporaryDirectory(prefix='newsboat-starred-') as directory:
        command,config=prepare_view(directory,rows)
        subprocess.run(command+['-x','reload'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        with config.open('a') as out:out.write('run-on-startup open\n')
        process = subprocess.Popen(command)
        handled = set()
        visible_ids = {str(row['id']) for row in rows}
        while True:
            try:
                process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                pass
            # Only explicit deletion (C), never read status, removes stars.
            with closing(sqlite3.connect(Path(directory)/'cache.db')) as db:
                removed = {str(row[0]) for row in db.execute('SELECT guid FROM rss_item WHERE deleted=1')}
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
            set_star(sys.argv[2],action=='save')
            subprocess.run(['notify-send','-a','Newsboat','-t','2000','Starred' if action=='save' else 'Unstarred'])
        elif action=='rebuild':rebuild_query(entries())
        elif action=='show':show()
        return 0
    except Exception as error:
        message=str(error) if isinstance(error,ValueError) else 'Could not reach Miniflux. Please try again when connected.'
        subprocess.run(['notify-send','-a','Newsboat','-t','5000','Starred unavailable',message])
        print(message,file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
