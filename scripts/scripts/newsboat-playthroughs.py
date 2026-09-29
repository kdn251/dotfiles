#!/usr/bin/env python3
"""Nested, offline playlist groups for explicitly downloaded playthroughs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import newsboat_media as media
import newsboat_playthroughs as library
from newsboat_loading import nested_view_environment

SCRIPTS=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('playlist_ui',SCRIPTS/'newsboat-playlists.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)


def prepare_view(directory, ident=None):
    groups=library.groups()
    if ident:
        group=next((g for g in groups if g['id']==ident),None)
        if group is None:
            group=next((g for g in library.read_groups() if g['id']==ident),None)
            if group:group=dict(group,rows=[])
        if group is None:raise ValueError('This playthrough is no longer available')
        data=dict(kind='playlist',name=group['name'],rows=group['rows'])
        title='🎮 '+group['name']+' — '+group['channel']
    else:
        group=None
        data=dict(kind='show',name=library.TITLE,rows=[dict(
            title=g['name']+' — '+g['channel'],
            url='newsboat-playthroughs://'+g['id']) for g in groups])
        title=library.TITLE
    command,config=ui.prepare_view(directory,data)
    lines=config.read_text().splitlines()
    lines=[line for line in lines if not line.startswith('articlelist-title-format ')]
    lines.append('articlelist-title-format '+json.dumps(' '+title.replace('%','%%'),ensure_ascii=False))
    if group is None:
        lines=[line for line in lines if not line.startswith('articlelist-format ')]
        lines.append('articlelist-format "%4i  %4w  %p %t"')
        action='python3 '+str(Path(__file__).resolve())+' group %u'
        lines=[line.replace(ui.command('playlist'),action) for line in lines]
        if not groups:
            p=Path(directory)/'playlist.xml'
            p.write_text(p.read_text().replace('No public playlists available — q to return','No playthroughs yet — download videos from a YouTube playlist'))
    else:
        if not group['rows']:
            p=Path(directory)/'playlist.xml'
            p.write_text(p.read_text().replace('No public videos available — q to return','No downloaded videos in this playthrough — q to return'))
        lines=[line for line in lines if not line.startswith('articlelist-format ')]
        lines.append('articlelist-format "%4i  %4w  %-9p %t"')
        # Retain every episode: deleting its local file makes it stream-only.
        media.atomic_write(Path(directory)/'urls',library.group_query(group['rows'])+'\n'+(Path(directory)/'playlist.xml').as_uri()+'\n')
        lines.append('prepopulate-query-feeds yes')
    config.write_text('\n'.join(lines)+'\n')
    return command,config,group


def show(ident=None):
    with tempfile.TemporaryDirectory(prefix='newsboat-playthroughs-') as directory:
        command,config,group=prepare_view(directory,ident)
        env=nested_view_environment(directory)
        env.pop('NEWSBOAT_THUMBNAILS',None)
        for key in ('NEWSBOAT_LIVE_QUERIES','NEWSBOAT_NESTED_VIEWS','NEWSBOAT_STARRED_VIEW','NEWSBOAT_STARRED_REMOVALS','NEWSBOAT_VODS_VIEW_DIR','NEWSBOAT_PLAYLIST_CONTEXT'):
            env.pop(key,None)
        if group:
            # Use the persistent manifest: detached retries can outlive this view.
            env['NEWSBOAT_PLAYLIST_CONTEXT']=str(library.directory()/(group['id']+'.json'))
            env['NEWSBOAT_PLAYTHROUGH_VIEW']=directory
            env['NEWSBOAT_PLAYTHROUGH_ID']=group['id']
        else:
            env.pop('NEWSBOAT_PLAYTHROUGH_VIEW',None)
            env.pop('NEWSBOAT_PLAYTHROUGH_ID',None)
        subprocess.run(command+['-x','reload'],env=env,capture_output=True,check=True,timeout=15)
        with config.open('a') as out:out.write('run-on-startup open\n')
        if group:
            from newsboat_thumbnails import run
            return run(command,env)
        return subprocess.call(command,env=env)


if __name__=='__main__':
    try:
        if sys.argv[1:2]==['rebuild']:
            with media.library_lock():library.publish()
        elif sys.argv[1:2]==['group']:
            if sys.argv[2]!='newsboat-playlists://empty':sys.exit(show(sys.argv[2].split('://',1)[-1]))
        else:sys.exit(show())
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        subprocess.run(['notify-send','-a','Newsboat','-t','5000','Playthroughs unavailable',str(error)])
        sys.exit(1)
