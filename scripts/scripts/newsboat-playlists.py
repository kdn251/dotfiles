#!/usr/bin/env python3
"""Browse a video's channel playlists and episodes in nested Newsboat lists."""
import json
import fcntl
import importlib.util
import os
from pathlib import Path
import re
import shlex
import signal
import select
import termios
import tty
import sqlite3
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import newsboat_youtube_playlists as library
from newsboat_media import atomic_write
from newsboat_loading import Renderer, nested_view_environment

SCRIPT = Path(__file__).resolve()
SCRIPTS = SCRIPT.parent


def command(action):
    return 'python3 '+shlex.quote(str(SCRIPT))+' '+action+' %u'


def fetch(kind, url, force=False):
    name, rows = library.videos(url, force) if kind == 'playlist' else library.playlists(url, force)
    data = dict(name=name, rows=rows, kind=kind)
    if kind=='playlist':
        data['url']=library.playlist_url(url)
        metadata=library.extract(data['url'])
        data['channel']=metadata.get('channel') or (rows[0]['source'] if rows else '')
        from newsboat_playthroughs import playlist_id
        context=library.LIBRARY/'browsed-playlists'/(playlist_id(url)+'.json')
        atomic_write(context,json.dumps(data,ensure_ascii=False))
        data['context']=str(context)
    return data


def loading(kind, url, force=False):
    """Keep fetching cancellable without leaving a hung browser command."""
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        child = subprocess.Popen([sys.executable,str(SCRIPT),'fetch',kind,url]+(['refresh'] if force else []),
                                 stdout=output,stderr=errors,start_new_session=True)
        renderer = None
        original = termios.tcgetattr(0)
        tick = 0
        caption = 'loading playlist videos' if kind=='playlist' else 'loading playlists'
        try:
            # Draw directly on the current screen. Curses was clearing it on
            # entry and switching screens again when handing off to Newsboat.
            tty.setcbreak(0)
            # Paint immediately, including for cached lists: leaving the old
            # terminal contents visible during startup caused a stale-screen flash.
            renderer = Renderer()
            while True:
                width,height=os.get_terminal_size(1)
                hint='q / Esc: cancel'[:max(0,width-1)]
                frame=renderer.draw(tick,caption)
                frame+=f'\x1b[{height};{max(1,(width-len(hint))//2+1)}H\x1b[2m{hint}\x1b[0m'.encode()
                sys.stdout.buffer.write(b'\x1b[?2026h'+frame+b'\x1b[?2026l')
                sys.stdout.buffer.flush();tick+=1
                if child.poll() is not None:break
                if select.select([0],[],[],.08)[0]:
                    key=os.read(0,1)
                    if not key or key in (b'q',b'\x1b'):return None
            if child.wait():
                errors.seek(0)
                raise ValueError(errors.read().decode(errors='replace').strip()[-400:] or 'Could not load playlists')
            output.seek(0)
            return json.load(output)
        finally:
            termios.tcsetattr(0,termios.TCSANOW,original)
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            if renderer is not None:renderer.close()


def prepare_view(directory, data):
    directory=Path(directory);is_playlist=data['kind']=='playlist'
    rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
    title=('Playlist · ' if is_playlist else 'Playlists · ')+data['name']
    for key,value in [('title',title),('link','https://www.youtube.com'),('description','YouTube playlists')]:
        ET.SubElement(channel,key).text=value
    for index,row in enumerate(data['rows'],1):
        item=ET.SubElement(channel,'item')
        # GUID order preserves YouTube's sequence without inventing publication dates.
        display_title = f"Episode {index} of {len(data['rows'])} · {row['title']}" if is_playlist else row['title']
        values={'title':display_title,'link':row['url'],'guid':f'{index:09d}',
                'author':(' '+row.get('source','')) if is_playlist else '',
                'description':row['title']}
        for key,value in values.items():ET.SubElement(item,key).text=value
    if not data['rows']:
        item=ET.SubElement(channel,'item')
        ET.SubElement(item,'title').text='No public '+('videos' if is_playlist else 'playlists')+' available — q to return'
        ET.SubElement(item,'guid').text='empty'
        ET.SubElement(item,'link').text='newsboat-playlists://empty'
    feed=directory/'playlist.xml';ET.ElementTree(rss).write(feed,encoding='utf-8',xml_declaration=True)
    (directory/'urls').write_text(feed.as_uri()+'\n')
    source=Path.home()/'.newsboat/config'
    if not source.exists():source=SCRIPTS.parents[1]/'newsboat/.newsboat/config'
    appearance={'color','highlight','highlight-article','scrolloff','text-width','datetime-format'}
    actions={'bind','bind-key','macro','browser'} if is_playlist else {'bind-key'}
    lines=[line for line in source.read_text().splitlines() if line.split() and line.split()[0] in appearance|actions]
    if not is_playlist:
        lines += [line for line in source.read_text().splitlines() if line.startswith(('bind ? ','bind h ','bind H ','macro p ','macro P ','macro z ','macro Z '))]
    lines=[line for line in lines if not line.startswith(('bind q ','bind o ','bind O ','bind P ','macro v ','macro d ','macro C '))]
    if is_playlist:
        for helper in ('commentary','favorites'):
            lines=[line.replace('python3 ~/scripts/newsboat-'+helper+'.py',
                    'python3 '+str(SCRIPT)+' collect '+helper) for line in lines]
    action=command('play' if is_playlist else 'playlist')
    browser_op='open-in-browser-noninteractively' if is_playlist else 'open-in-browser'
    lines += ['urls-source local','auto-reload no','show-read-feeds yes','show-read-articles yes',
              'confirm-exit no','article-sort-order guid-asc','articlelist-title-format " %T"',
              'searchresult-title-format " Search results"',
              'articlelist-format '+json.dumps('%4i  %-9p %-20a │ %t' if is_playlist else '%4i  %p %t',ensure_ascii=False),
              'browser '+json.dumps(action),
              'bind q articlelist hard-quit -- "Back"']
    for key in ('<ENTER>','o','O','l'):
        lines.append(f'bind {key} articlelist,searchresultslist set browser '+json.dumps(action)+' ; '+browser_op+
                     (' ; toggle-article-read "read" "stay"' if is_playlist else '')+' -- "'+('Play video' if is_playlist else 'Open playlist')+'"')
    if not is_playlist:
        lines=[line for line in lines if not line.startswith(('bind o ','bind O '))]
        for key in ('o','O'):
            lines.append(f'bind {key} articlelist,searchresultslist set browser '+json.dumps(command('resume'))+' ; open-in-browser-noninteractively -- "Resume playlist (Enter browses episodes)"')
    lines.append('bind P articlelist,article,searchresultslist set browser '+json.dumps(command('show'))+' ; open-in-browser -- "Browse creator playlists"')
    if is_playlist:
        lines += ['macro v set browser '+json.dumps(command('play'))+' ; open-in-browser-noninteractively ; toggle-article-read "read" "stay" -- "Play video"',
                  'macro d set browser '+json.dumps(command('download'))+' ; open-in-browser-noninteractively ; toggle-article-read "read" -- "Download video and mark read"']
    else:
        lines.append('macro d set browser '+json.dumps(command('download-playlist'))+' ; open-in-browser-noninteractively -- "Download this whole playlist to Playthroughs"')
        lines.append('macro D set browser '+json.dumps(str(SCRIPT.with_name('delete-downloaded.sh'))+' %u')+' ; open-in-browser-noninteractively -- "Delete this playlist’s downloaded videos"')
    config=directory/'config';config.write_text('\n'.join(lines)+'\n')
    binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
    return [str(binary) if binary.exists() else 'newsboat','-q','-C',str(config),'-u',str(directory/'urls'),'-c',str(directory/'cache.db')],config


def show(kind, url):
    if url=='newsboat-playlists://empty':return 0
    data=loading(kind,url)
    if data is None:return 0
    with tempfile.TemporaryDirectory(prefix='newsboat-playlists-') as directory:
        cmd,config=prepare_view(directory,data)
        env=nested_view_environment(directory)
        env.pop('NEWSBOAT_THUMBNAILS',None)
        for name in ('NEWSBOAT_LIVE_QUERIES','NEWSBOAT_NESTED_VIEWS','NEWSBOAT_STARRED_VIEW','NEWSBOAT_STARRED_REMOVALS','NEWSBOAT_VODS_VIEW_DIR'):
            env.pop(name,None)
        env['NEWSBOAT_CACHE']=str(library.CACHE)
        env['NEWSBOAT_PLAYLIST_VIEW']='1'
        env['NEWSBOAT_UNDO_HELPER']=str(SCRIPTS/'newsboat-starred.py')
        if data.get('context'):env['NEWSBOAT_PLAYLIST_CONTEXT']=data['context']
        else:env.pop('NEWSBOAT_PLAYLIST_CONTEXT',None)
        subprocess.run(cmd+['-x','reload'],env=env,check=True,capture_output=True,timeout=15)
        with config.open('a') as out:
            out.write('run-on-startup open\n')
            if kind == 'playlist':
                from newsboat_thumbnails import supported
                if supported(env):
                    # The creator is shared by the whole playlist; leave room
                    # for episode titles alongside the image pane.
                    out.write('articlelist-format "%4i  %-9p %t"\n')
                    channel = data.get('channel') or next((r.get('source') for r in data['rows'] if r.get('source')), '')
                    title = ' Playlist · '+data['name']+(' — '+channel if channel else '')
                    out.write('articlelist-title-format '+json.dumps(title.replace('%','%%'),ensure_ascii=False)+'\n')
        from newsboat_thumbnails import run
        return run(cmd,env)


def background(args):
    subprocess.Popen([sys.executable,str(SCRIPT),'work',*args],stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def work(action, url, extra=()):
    if action=='resume':
        from newsboat_resume import playlist_row, launch
        data=fetch('playlist',url)
        return launch(playlist_row(data['rows']),data['context'])
    if action=='download-playlist':return download_playlist(url)
    url=library.video_url(url)
    if action=='download':
        if context:=os.environ.get('NEWSBOAT_PLAYLIST_CONTEXT'):
            from newsboat_playthroughs import record
            record(url,context)
        result = subprocess.call([str(SCRIPTS/'newsboat-download-video.sh'),url])
        try:
            library.ensure_entry(url)
            from newsboat_media import rebuild
            rebuild()
        except (OSError,ValueError,sqlite3.Error):
            pass  # The persistent downloader can still wait for connectivity.
        return result
    if action=='collect':
        helper,operation=extra
        if helper not in ('commentary','favorites') or operation not in ('save','remove','restore'):
            raise ValueError('Unknown collection action')
        from newsboat_actions import begin, finish
        marker=begin(url,remove=helper if operation=='remove' else '')
        try:
            library.ensure_entry(url)
            return subprocess.call([sys.executable,str(SCRIPTS/f'newsboat-{helper}.py'),operation,url])
        finally:
            finish(marker)
    else:
        row=library.saved_item(url) or {}
        launcher=[str(SCRIPTS/'newsboat-play-video.sh'),url,row.get('title','')]
    return subprocess.call(launcher)


def downloader_module():
    spec=importlib.util.spec_from_file_location('playlist_downloader',SCRIPTS/'newsboat-download.py')
    downloader=importlib.util.module_from_spec(spec);spec.loader.exec_module(downloader)
    return downloader


def download_playlist(url):
    from newsboat_playthroughs import playlist_id, record_rows, read_groups
    from newsboat_media import rebuild
    saved = None
    if url.startswith('newsboat-playthroughs://'):
        ident = url.split('://', 1)[1]
        saved = next((group for group in read_groups() if group['id'] == ident), None)
        if saved is None:
            raise ValueError('This saved playlist is no longer available')
        url = saved['url']
    url=library.playlist_url(url)
    library.LIBRARY.mkdir(parents=True,exist_ok=True)
    with (library.LIBRARY/('batch-'+playlist_id(url)+'.lock')).open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        subprocess.run(['notify-send','-a','Newsboat','-t','4000','Preparing playlist download','Loading the playlist’s available videos…'])
        data=saved if saved is not None else fetch('playlist',url)
        rows=list({row['url']:row for row in data['rows']}.values())
        if not rows:raise ValueError('This playlist has no available videos to download')
        record_rows(data,rows)
        downloader=downloader_module()
        failures=[]
        try:
            for row in rows:
                try:downloader.enqueue(row['url'],row['title'],batch=url,defer=True)
                except (OSError,ValueError):failures.append(row['title'])
        finally:
            downloader.start_watcher()
            rebuild()
        if failures:raise ValueError(f"Could not queue {len(failures)} videos; the other videos are queued in Playthroughs")
        subprocess.run(['notify-send','-a','Newsboat','-t','5000','Downloading playlist: '+data['name'],
                        f'{len(rows)} videos in Playthroughs · up to 3 downloads at a time. Existing downloads are reused.'])
        return 0


def request(url):
    url=library.browse_url(url)
    target=os.environ.get('NEWSBOAT_PLAYLIST_REQUEST')
    if not target or not Path(target).parent.is_dir():
        raise ValueError('Restart Newsboat, then reopen this video to use playlists from MPV')
    atomic_write(Path(target),url)
    address=os.environ.get('NEWSBOAT_WINDOW_ADDRESS','')
    if re.fullmatch(r'0x[0-9a-fA-F]+',address):
        subprocess.run(['hyprctl','dispatch','focuswindow','address:'+address],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def main(args):
    if args[0]=='fetch':
        print(json.dumps(fetch(args[1],args[2],len(args)>3)));return 0
    if args[0]=='request':request(args[1]);return 0
    if args[0] in ('show','playlist'):return show(args[0],args[1])
    if args[0]=='work':
        if args[1]=='collect':return work('collect',args[4],args[2:4])
        return work(args[1],args[2])
    if args[0] in ('play','resume','download','download-playlist','collect'):
        if args[-1]=='newsboat-playlists://empty':return 0
        background(args);return 0
    raise ValueError('Unknown playlist command')


if __name__=='__main__':
    try:sys.exit(main(sys.argv[1:]))
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        if sys.argv[1:2]==['fetch']:print(str(error),file=sys.stderr)
        else:subprocess.run(['notify-send','-a','Newsboat','-t','5000','Playlists unavailable',str(error)])
        sys.exit(1)
