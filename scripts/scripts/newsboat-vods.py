#!/usr/bin/env python3
"""Newsboat inventory/view for the scheduled Twitch VOD downloads."""
from email.utils import formatdate
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import newsboat_vod_progress as progress
import xml.etree.ElementTree as ET
import newsboat_media as media

SCRIPTS = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
DIRECTORY = media.ROOT/'twitch-vods'
INDEX = STATE/'vod-items.json'
TITLE = '🎬 VODs'
PREFIX = 'query:'+TITLE+':'


def entries():
    try:
        return [row for row in json.loads(INDEX.read_text()) if Path(row['path']).is_file()]
    except (OSError, ValueError):
        return []


def scan():
    old = {row['path']: row for row in entries()}
    busy = media.busy_paths()
    rows = {}
    probe_index = STATE/'vod-probes.json'
    try:
        previous_probes = json.loads(probe_index.read_text())
    except (OSError, ValueError):
        previous_probes = {}
    probes = {}
    # Only the daily downloader's top-level files; ,d downloads live in manual/.
    for path in DIRECTORY.glob('*'):
        if path.suffix.lower() not in media.MEDIA or not path.is_file() or not media.inside(path):
            continue
        if path.resolve() in busy or any(Path(str(path)+suffix).exists() for suffix in ('.part','.ytdl','.incomplete')):
            continue
        key = media.filename_identity(path)
        parts = path.stem.split(' - ',1)
        if not key or key[0] != 'twitch' or len(parts) != 2:
            continue
        stat = path.stat()
        signature = [stat.st_size,stat.st_mtime_ns]
        row = old.get(str(path))
        if not row or row.get('signature') != signature:
            cached = previous_probes.get(str(path), {})
            valid = cached.get('valid') if cached.get('signature') == signature else media.playable(path)
            probes[str(path)] = dict(signature=signature, valid=valid)
            if not valid:
                continue
            row = dict(url='https://www.twitch.tv/videos/'+key[1], title=parts[1].rsplit(' - ',1)[0],
                       source=parts[0], id=key[1], path=str(path), saved=stat.st_mtime, signature=signature)
        previous = rows.get(key[1])
        if not previous or row['saved'] > previous['saved']:
            rows[key[1]] = row
    media.atomic_write(probe_index,json.dumps(probes))
    return sorted(rows.values(),key=lambda row:int(row['id']),reverse=True)


def query(rows):
    terms = ' or '.join('link = '+json.dumps(row['url']) for row in rows)
    return json.dumps(PREFIX+(terms or 'link = "newsboat-vods://empty"'),ensure_ascii=False)


def rebuild():
    with media.library_lock():
        rows = scan()
        media.atomic_write(INDEX,json.dumps(rows,ensure_ascii=False))
        progress.publish_count(progress.active_rows(),state=STATE)
        if media.URLS.exists():
            lines = [line for line in media.URLS.read_text().splitlines() if not line.startswith('"'+PREFIX)]
            position = next((i for i,line in enumerate(lines) if line.startswith(('"query: Favorites:', '"query:🌎 All:'))),len(lines))
            lines.insert(position,query(rows))
            text = '\n'.join(lines)+'\n'
            if text != media.URLS.read_text():
                media.atomic_write(media.URLS,text)
    return rows


def write_view(directory, rows):
    directory = Path(directory)
    rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
    for name,value in [('title',TITLE),('link','https://localhost/vods'),('description','Downloaded Twitch VODs')]:
        ET.SubElement(channel,name).text=value
    for row in rows:
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text=row['title']
        ET.SubElement(item,'author').text=' '+row['source']
        ET.SubElement(item,'link').text=row['url']
        ET.SubElement(item,'guid',isPermaLink='false').text='vod-'+row['id']
        ET.SubElement(item,'description').text='Downloaded Twitch VOD from '+row['source']
        ET.SubElement(item,'pubDate').text=formatdate(row['saved'],usegmt=True)
    if not rows:
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text='No downloaded VODs — new downloads will appear here'
        ET.SubElement(item,'link').text='newsboat-vods://empty'
        ET.SubElement(item,'guid',isPermaLink='false').text='empty-vods'
    path=directory/'vods.xml'
    ET.ElementTree(rss).write(path,encoding='utf-8',xml_declaration=True)
    media.atomic_write(directory/'urls',query(rows)+'\n'+path.as_uri()+'\n')


def refresh_background():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE/'vod-refresh.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        rebuild()


def view_entries():
    # Opening a list must never wait for ffprobe or a downloader's library lock.
    busy = media.busy_paths()
    rows = [row for row in entries() if Path(row['path']).resolve() not in busy
            and not any(Path(row['path']+suffix).exists() for suffix in ('.part','.ytdl','.incomplete'))]
    subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'refresh'],
                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     start_new_session=True)
    active = progress.active_rows()
    active_urls = {row['url'] for row in active}
    # Publish a byte counter immediately; metadata/percentage are filled in off-thread.
    progress.publish(active,{})
    return sorted(active + [row for row in rows if row['url'] not in active_urls],
                  key=lambda row: (not row.get('active',False), -int(row.get('id',0))))


def prepare_view(directory):
    rows=view_entries()
    spec=importlib.util.spec_from_file_location('history',SCRIPTS/'newsboat-history.py')
    history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)
    command,config=history.prepare_view(directory)
    write_view(directory,rows)
    lines=[line for line in config.read_text().splitlines() if not line.startswith(
        ('macro D ','macro C ','bind o ','bind O ','macro v ','article-sort-order '))]
    action='set browser "python3 ~/scripts/newsboat-vods.py play %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" ; toggle-article-read "read" "stay"'
    lines += ['articlelist-format " %f  %D  %-9p %-20a │ %t"',
              'article-sort-order date-asc', 'prepopulate-query-feeds yes',
              'bind o articlelist,article,searchresultslist '+action,
              'bind O articlelist,article,searchresultslist '+action,
              'macro v '+action,
              'macro D set browser "python3 ~/scripts/newsboat-vods.py delete %u" ; open-in-browser-noninteractively ; set browser "~/scripts/newsboat-brave-app.sh %u" ; reload-urls -- "Delete this local VOD"']
    config.write_text('\n'.join(lines)+'\n')
    return command,config


def delete(url):
    key=media.identity(url)
    if not key or key[0] != 'twitch':
        raise ValueError('Select a downloaded Twitch VOD')
    with media.library_lock():
        busy=media.busy_paths()
        paths=[path for path in DIRECTORY.glob('*') if path.is_file() and media.inside(path)
               and media.filename_identity(path)==key]
        if any(path.resolve() in busy or Path(str(path)+'.incomplete').exists() for path in paths):
            raise ValueError('This VOD is still downloading')
        for path in paths:
            if path.suffix.lower() in media.MEDIA:
                path.unlink()
        # Preserve .downloaded-twitch-vods: deletion should not schedule a re-download.
        media.rebuild_unlocked()
    rows=rebuild()
    if directory:=os.environ.get('NEWSBOAT_VODS_VIEW_DIR'):
        write_view(directory,rows)


def play(url):
    if any(row['url']==url for row in progress.active_rows()):
        raise ValueError('This VOD is still downloading; its progress is shown in the list')
    row=next((row for row in entries() if row['url']==url),None)
    if not row:
        raise ValueError('This VOD is no longer on disk; reopen VODs to refresh the list')
    subprocess.run([sys.executable,str(SCRIPTS/'newsboat-play-video.py'),url,row['title']],check=True)


def show():
    with tempfile.TemporaryDirectory(prefix='newsboat-vods-') as directory:
        command,config=prepare_view(directory)
        subprocess.run(command+['-x','reload'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        with config.open('a') as out:
            out.write('run-on-startup open\n')
        env=dict(os.environ,NEWSBOAT_VODS_VIEW_DIR=directory)
        env.pop('NEWSBOAT_UNDO_HELPER',None)
        # Keep the query inside this local view instead of nesting VODs again.
        env.pop('NEWSBOAT_NESTED_VIEWS',None)
        subprocess.Popen([sys.executable,str(SCRIPTS/'newsboat_vod_progress.py')],
                         stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return subprocess.call(command,env=env)


if __name__=='__main__':
    try:
        action=sys.argv[1]
        if action=='show':sys.exit(show())
        elif action=='rebuild':rebuild()
        elif action=='refresh':refresh_background()
        elif action=='delete':delete(sys.argv[2])
        elif action=='play':play(sys.argv[2])
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        subprocess.run(['notify-send','-a','Newsboat','-t','5000','VODs unavailable',str(error)])
        sys.exit(1)
