"""Persistent ordered viewing queue, independent of download and feed lifetimes."""
from contextlib import closing
from email.utils import formatdate
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
import newsboat_media as media

TITLE = '📺 Queue'
PREFIX = 'query:'+TITLE+':'
SCRIPTS = Path(__file__).resolve().parent


def state():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'


def entries():
    try:return json.loads((state()/'viewing-queue.json').read_text())
    except FileNotFoundError:return []


def identity(url):
    ident=media.identity(url)
    return ':'.join(ident) if ident else url


def metadata(url):
    title,source=url,''
    cache=Path(os.environ.get('NEWSBOAT_CACHE',Path.home()/'.newsboat/cache.db'))
    try:
        with closing(sqlite3.connect(cache.as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
            row=db.execute('SELECT i.title,f.title,i.feedurl,i.author FROM rss_item i LEFT JOIN rss_feed f ON i.feedurl=f.rssurl WHERE i.url=? ORDER BY i.id DESC LIMIT 1',(url,)).fetchone()
            if row:
                from newsboat_sources import feed_titles
                title,source,feed,author=row
                source=source or feed_titles(state()).get(feed,'') or author or ''
    except sqlite3.Error:pass
    context=os.environ.get('NEWSBOAT_PLAYLIST_CONTEXT')
    if context:
        try:
            data=json.loads(Path(context).read_text())
            for row in data.get('rows',[]):
                if identity(row.get('url',''))==identity(url):
                    title=row.get('title') or title
                    source=row.get('source') or data.get('channel') or source
                    break
        except (OSError,ValueError):pass
    if title==url:title=media.cached_title(url) or title
    return dict(url=url,title=title,source=source or '')


def publish(rows):
    import newsboat_queue_time as queue_time
    if queue_time.publish(rows):queue_time.start_worker()
    media.atomic_write(state()/'starred-urls.txt.queue.count',str(len(rows))+'\n')
    media.atomic_write(state()/'viewing-queue.tsv',''.join(row['url']+'\t'+row['queue_token']+'\n' for row in rows))
    urls=Path(os.environ.get('NEWSBOAT_URLS_FILE',Path.home()/'.newsboat/urls'))
    # Serialize with the other generated collections, preserving their changes.
    with media.library_lock():
        if not urls.exists():return
        original=urls.read_text()
        lines=[line for line in original.splitlines() if not line.startswith('"'+PREFIX)]
        if rows:
            lines.insert(0,json.dumps(PREFIX+'link = "newsboat-queue://placeholder"',ensure_ascii=False))
        text='\n'.join(lines)+'\n'
        if text!=original:media.atomic_write(urls,text)


def read_state(name, default=None):
    try:return json.loads((state()/name).read_text())
    except (OSError,ValueError):return default


def undo_path(token):
    return state()/'queue-undo'/(hashlib.sha256(token.encode()).hexdigest()+'.json')


def checkpoint(rows, url, token):
    """Called under the queue lock, immediately before the requested change."""
    index=next((i for i,row in enumerate(rows) if identity(row['url'])==identity(url)),None)
    navigation=read_state('queue-navigation.json',[])
    nav_index=next((i for i,row in enumerate(navigation) if identity(row['url'])==identity(url)),None)
    snapshot=dict(url=url,index=index,row=rows[index] if index is not None else None,
                  nav_index=nav_index,nav_row=navigation[nav_index] if nav_index is not None else None,
                  current=read_state('queue-current.json'))
    path=undo_path(token);path.parent.mkdir(parents=True,exist_ok=True)
    media.atomic_write(path,json.dumps(snapshot,ensure_ascii=False))


def restore(rows,url,token):
    snapshot=json.loads(undo_path(token).read_text())
    if identity(snapshot['url'])!=identity(url):raise ValueError('Queue undo URL mismatch')
    ident=identity(url)
    rows=[row for row in rows if identity(row['url'])!=ident]
    if snapshot['row'] is not None:
        rows.insert(min(snapshot['index'],len(rows)),snapshot['row'])
    navigation=[row for row in read_state('queue-navigation.json',[]) if identity(row['url'])!=ident]
    if snapshot['nav_row'] is not None:
        navigation.insert(min(snapshot['nav_index'],len(navigation)),snapshot['nav_row'])
    elif snapshot['row'] is not None:
        # Preserve restored FIFO placement even if navigation started later.
        navigation.insert(min(snapshot['index'],len(navigation)),snapshot['row'])
    media.atomic_write(state()/'queue-navigation.json',json.dumps(navigation,ensure_ascii=False))
    saved=snapshot['current'];current=read_state('queue-current.json')
    if saved and identity(saved['url'])==ident and snapshot['row'] is not None:
        # Do not replace a different video that started playing since the action.
        if not current or identity(current['url'])==ident:
            media.atomic_write(state()/'queue-current.json',json.dumps(saved,ensure_ascii=False))
    elif current and identity(current['url'])==ident and snapshot['row'] is None:
        (state()/'queue-current.json').unlink(missing_ok=True)
    return rows


def change(action,url='',token=''):
    root=state();root.mkdir(parents=True,exist_ok=True)
    with (root/'viewing-queue.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=entries();ident=identity(url)
        if action in ('add','remove') and os.environ.get('NEWSBOAT_QUEUE_UNDO_TOKEN'):
            checkpoint(rows,url,os.environ['NEWSBOAT_QUEUE_UNDO_TOKEN'])
        if action=='add' and not rows:
            (root/'queue-navigation.json').unlink(missing_ok=True)
        if action=='add':
            if not media.identity(url) or any(c in url for c in '\r\n\t'):
                raise ValueError('Queue supports YouTube videos and Twitch VODs')
            if not any(identity(row['url'])==ident for row in rows):
                rows.append(dict(metadata(url),queue_token=uuid.uuid4().hex))
        elif action in ('remove','started','finished'):
            if action=='started':
                current=next((row for row in rows if identity(row['url'])==ident and row['queue_token']==token),None)
                if current:media.atomic_write(root/'queue-current.json',json.dumps(current,ensure_ascii=False))
            if action=='remove':
                try:
                    path=root/'queue-navigation.json'
                    history=json.loads(path.read_text())
                    media.atomic_write(path,json.dumps([row for row in history if identity(row['url'])!=ident],ensure_ascii=False))
                except (OSError,ValueError):pass
            if action!='started':
                rows=[row for row in rows if not (identity(row['url'])==ident and
                      (action=='remove' or row['queue_token']==token))]
                try:
                    current=json.loads((root/'queue-current.json').read_text())
                    if identity(current['url'])==ident and (action=='remove' or current['queue_token']==token):
                        (root/'queue-current.json').unlink(missing_ok=True)
                except (OSError,ValueError):pass
        elif action in ('move-before','move-after'):
            source=next((row for row in rows if identity(row['url'])==ident),None)
            target=next((row for row in rows if identity(row['url'])==identity(token)),None)
            if source is None or target is None:raise ValueError('Selected video is no longer in Queue')
            if source==target:return
            if os.environ.get('NEWSBOAT_QUEUE_UNDO_TOKEN'):
                checkpoint(rows,url,os.environ['NEWSBOAT_QUEUE_UNDO_TOKEN'])
            history=read_state('queue-navigation.json',[])
            seen={row['queue_token'] for row in history}
            history += [row for row in rows if row['queue_token'] not in seen]
            def move(items):
                items=[row for row in items if row['queue_token']!=source['queue_token']]
                at=next(i for i,row in enumerate(items) if row['queue_token']==target['queue_token'])
                items.insert(at+(action=='move-after'),source)
                return items
            rows=move(rows)
            media.atomic_write(root/'queue-navigation.json',json.dumps(move(history),ensure_ascii=False))
        elif action=='restore':
            rows=restore(rows,url,token)
        elif action=='refresh':
            for row in rows:
                if not row.get('source'):
                    details=metadata(row['url'])
                    row['source']=details['source']
                    if row['title']==row['url']:row['title']=details['title']
        else:raise ValueError('Unknown queue action')
        old=entries()
        if rows!=old or not (root/'viewing-queue.json').exists():
            media.atomic_write(root/'viewing-queue.json',json.dumps(rows,ensure_ascii=False))
        publish(rows)


def prepare_view(directory):
    change('refresh')
    spec=importlib.util.spec_from_file_location('queue_history',SCRIPTS/'newsboat-history.py')
    history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)
    command,config=history.prepare_view(directory)
    rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
    for name,value in [('title',TITLE),('link','newsboat-queue://home'),('description','yy picks up a row; p moves below, P above; U undoes; ,W removes an entry.')]:
        ET.SubElement(channel,name).text=value
    from newsboat_sources import source_label
    for i,row in enumerate(entries()):
        item=ET.SubElement(channel,'item')
        for name,value in [('title',row['title']),('link',row['url']),('author',source_label(row['url'],row.get('source',''))),
                           ('guid',row['queue_token']),('pubDate',formatdate(1700000000+i,usegmt=True))]:
            ET.SubElement(item,name).text=value
    ET.ElementTree(rss).write(Path(directory)/'history.xml',encoding='utf-8',xml_declaration=True)
    lines=[line for line in config.read_text().splitlines() if not line.startswith(('macro C ','article-sort-order ','articlelist-format '))]
    lines += ['article-sort-order date-asc','articlelist-format "%4i  %4w  %-9p %-20a │ %t"',
              'articlelist-title-format " '+TITLE+'"',
              'bind yy articlelist,searchresultslist undo-checkpoint queue-yank -- "Pick up Queue row; p moves below, P above"',
              'bind p articlelist,searchresultslist undo-checkpoint queue-after -- "Move picked-up Queue row below this row"',
              'bind P articlelist,searchresultslist undo-checkpoint queue-before -- "Move picked-up Queue row above this row"']
    config.write_text('\n'.join(lines)+'\n')
    return command,config


def show():
    with tempfile.TemporaryDirectory(prefix='newsboat-queue-') as directory:
        command,config=prepare_view(directory)
        from newsboat_loading import nested_view_environment
        env=nested_view_environment(directory)
        for name in ('NEWSBOAT_PLAYLIST_CONTEXT','NEWSBOAT_STARRED_VIEW','NEWSBOAT_STARRED_REMOVALS','NEWSBOAT_PLAYTHROUGH_ID','NEWSBOAT_PLAYTHROUGH_VIEW','NEWSBOAT_LIVE_QUERIES','NEWSBOAT_NESTED_VIEWS','NEWSBOAT_UNDO_HELPER'):
            env.pop(name,None)
        env['NEWSBOAT_QUEUE_VIEW']='1'
        env['NEWSBOAT_QUEUE_STATUS']=str(state()/'viewing-queue.tsv')
        subprocess.run(command+['-x','reload'],env=env,check=True,capture_output=True,timeout=15)
        with config.open('a') as out:out.write('run-on-startup open\n')
        from newsboat_thumbnails import run
        return run(command,env)


def navigation(current):
    root=state();root.mkdir(parents=True,exist_ok=True)
    with (root/'viewing-queue.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        rows=entries()
        path=root/'queue-navigation.json'
        try:history=json.loads(path.read_text())
        except (OSError,ValueError):history=[]
        seen={row['queue_token'] for row in history}
        history += [row for row in rows if row['queue_token'] not in seen]
        text=json.dumps(history,ensure_ascii=False)
        if not path.exists() or path.read_text()!=text:media.atomic_write(path,text)
        index=next((i for i,row in enumerate(history) if identity(row['url'])==identity(current)),None)
        if index is None:
            first=rows[0] if rows else None
            return first,None,first
        live={row['queue_token'] for row in rows}
        following=next((row for row in history[index+1:] if row['queue_token'] in live),None)
        previous=history[index-1] if index else None
        following_manual=history[index+1] if index+1<len(history) else None
        return following,previous,following_manual


def resume():
    from newsboat_resume import launch
    os.environ['NEWSBOAT_QUEUE_PLAYBACK']='1'
    # Homepage playback follows the current queue order; mpv restores position.
    rows=entries()
    return launch(rows[0] if rows else None)


if __name__=='__main__':
    if sys.argv[1]=='show':sys.exit(show())
    elif sys.argv[1]=='resume':sys.exit(resume())
    else:change(*sys.argv[1:])
