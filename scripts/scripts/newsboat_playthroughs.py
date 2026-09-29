"""Saved full playlists, explicit download membership, and Playthroughs progress."""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import newsboat_media as media

TITLE = '🎮 Playthroughs'
PREFIX = 'query:'+TITLE+':'
GROUP_PREFIX = 'query:🎮 Playthrough:'


def directory():
    return media.STATE.parent/'youtube-playlists/playthroughs'


def playlist_id(url):
    from newsboat_youtube_playlists import playlist_url
    return parse_qs(urlparse(playlist_url(url)).query)['list'][0]


def read_groups():
    for path in directory().glob('*.json'):
        try:
            row = json.loads(path.read_text())
            if row.get('schema',1)<2:
                row['selected_urls']=[video['url'] for video in row.get('rows',[])]
                try:
                    catalog=json.loads((directory().parent/'browsed-playlists'/path.name).read_text())
                    if catalog.get('rows'):row['rows']=catalog['rows']
                except (OSError,ValueError):pass
                row['schema']=2
            if row.get('rows'):yield row
        except (OSError, ValueError):pass


def record(url, context):
    """Only an explicit download request enrolls a video in this library."""
    data = json.loads(Path(context).read_text())
    row = next((r for r in data['rows'] if media.identity(r['url']) == media.identity(url)), None)
    if row is None:raise ValueError('This video is missing from the selected playlist')
    record_rows(data,[row])


def record_rows(data, selected=None):
    selected=data['rows'] if selected is None else selected
    if not selected:return
    ident = playlist_id(data['url'])
    with media.library_lock():
        path = directory()/(ident+'.json')
        group=next((g for g in read_groups() if g['id']==ident),dict(id=ident,url=data['url'],rows=[],selected_urls=[]))
        group.update(name=data['name'],channel=data.get('channel') or selected[0]['source'])
        rows={r['url']:r for r in group['rows']}
        rows.update({row['url']:row for row in data['rows']})
        group['schema']=2
        group['selected_urls']=sorted(set(group['selected_urls'])|{row['url'] for row in selected})
        group['rows']=sorted(rows.values(),key=lambda r:r['position'])
        media.atomic_write(path,json.dumps(group,ensure_ascii=False))


def member_keys():
    return {media.identity(url) for group in read_groups() for url in group['selected_urls']}


def active_keys(index=None):
    if index is None:
        try:index=json.loads((media.STATE/'.media-index.json').read_text())
        except (OSError,ValueError):index={}
    keys={media.filename_identity(Path(path)) for path,value in index.items()
          if value.get('valid') and Path(path).is_file()}
    keys.update(media.identity(job['url']) for _,job in media.records()
                if job.get('status') in {'preparing','downloading','processing','retrying','waiting','failed','cancelled'})
    return keys


def groups(index=None):
    return sorted(read_groups(),key=lambda g:(g['channel'].casefold(),g['name'].casefold()))


def group_query(rows):
    terms=' or '.join('link = '+json.dumps(row['url']) for row in rows)
    return json.dumps(GROUP_PREFIX+(terms or 'link = "newsboat-playlists://empty"'),ensure_ascii=False)


def with_group_progress(content, current=None):
    """Average the displayed video percentages; unwatched videos count as zero."""
    lines=[line for line in content.splitlines() if not line.startswith('newsboat-playthroughs://')]
    watched={}
    for line in lines:
        try:
            url,value=line.split('\t',1)
            key=media.identity(url)
            if key:watched[key]=max(0,min(100,int(value.rstrip('%'))))
        except ValueError:pass
    for group in groups() if current is None else current:
        videos={media.identity(row['url']) for row in group['rows']}
        percent=sum(watched.get(key,0) for key in videos)//len(videos) if videos else 0
        lines.append(f"newsboat-playthroughs://{group['id']}\t{percent}%")
    return '\n'.join(lines)+('\n' if lines else '')


def publish(index=None):
    """Called under the shared media lock; never probe files or fetch YouTube."""
    current=groups(index)
    for group in current:
        path=directory()/(group['id']+'.json')
        if json.loads(path.read_text()).get('schema',1)<2:
            media.atomic_write(path,json.dumps(group,ensure_ascii=False))
    target=media.STATE.parent/'download-status.tsv.watched'
    previous=target.read_text() if target.exists() else ''
    updated_progress=with_group_progress(previous,current)
    if updated_progress!=previous:media.atomic_write(target,updated_progress)
    count=media.STATE.parent/'starred-urls.txt.playthroughs.count'
    old=count.read_text() if count.exists() else ''
    value=str(len(current))+'\n'
    if old!=value:media.atomic_write(count,value)
    if media.URLS.exists():
        text=media.URLS.read_text()
        lines=[line for line in text.splitlines() if not line.startswith('"'+PREFIX)]
        fallback=next((i+1 for i,line in enumerate(lines) if line.startswith('"query:📥 Downloads:')),0)
        pos=next((i for i,line in enumerate(lines) if line.startswith(('"query:🎬 VODs:', '"query:📚 Books:', '"query: Favorites:', '"query:🌎 All:'))),fallback)
        lines.insert(pos,json.dumps(PREFIX+'link = "newsboat-playthroughs://empty"',ensure_ascii=False))
        updated='\n'.join(lines)+'\n'
        if updated!=text:media.atomic_write(media.URLS,updated)
        elif old!=value:os.utime(media.URLS,None)
    view=os.environ.get('NEWSBOAT_PLAYTHROUGH_VIEW')
    if view and Path(view).is_dir():
        ident=os.environ.get('NEWSBOAT_PLAYTHROUGH_ID')
        selected=next((g['rows'] for g in current if g['id']==ident),[])
        feed=(Path(view)/'playlist.xml').as_uri()
        media.atomic_write(Path(view)/'urls',group_query(selected)+'\n'+feed+'\n')
    return current


def delete_downloads(url):
    """Delete exact episode identities using only the locally saved catalog."""
    ident = url.split('://', 1)[1] if url.startswith('newsboat-playthroughs://') else playlist_id(url)
    group = next((g for g in read_groups() if g['id'] == ident), None)
    if group is None:
        return 0
    urls = list(dict.fromkeys(row['url'] for row in group['rows']))
    token = os.environ.get('NEWSBOAT_DOWNLOAD_UNDO_TOKEN')
    children = [(item, token+':'+str(i)) for i, item in enumerate(urls)] if token else []
    if token:
        from newsboat_download_undo import directory
        folder = directory(token)
        folder.mkdir(parents=True, mode=0o700, exist_ok=False)
        media.atomic_write(folder/'manifest.json', json.dumps(dict(url=url, children=children)))
    count = 0
    failures = []
    try:
        for i, item in enumerate(urls):
            if token:
                os.environ['NEWSBOAT_DOWNLOAD_UNDO_TOKEN'] = children[i][1]
            try:
                count += media.delete(item, refresh=False)
            except (OSError, ValueError) as error:
                failures.append(str(error))
    finally:
        if token:
            os.environ['NEWSBOAT_DOWNLOAD_UNDO_TOKEN'] = token
        media.rebuild()
    if failures:
        raise ValueError(f'Deleted {count} files; {len(failures)} episodes could not be removed: '+failures[0])
    return count
