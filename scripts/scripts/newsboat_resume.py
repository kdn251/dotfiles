"""Choose a saved collection's next video using the existing playback progress."""
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import sqlite3
import newsboat_media as media


def progress():
    path=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'newsboat/watch-progress.db'
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
            return {key:(fraction,updated) for key,fraction,updated in db.execute('SELECT identity,fraction,updated FROM progress')}
    except sqlite3.Error:return {}


def key(row):
    identity=media.identity(row['url'])
    return ':'.join(identity) if identity else row['url']


def playlist_row(rows):
    if not rows:return None
    watched=progress()
    touched=[(i,watched[key(row)]) for i,row in enumerate(rows) if key(row) in watched]
    if not touched:return rows[0]
    index,(fraction,_)=max(touched,key=lambda entry:entry[1][1])
    if fraction<.95:return rows[index]
    # Continue after the last episode watched; wrap only to an unfinished one.
    for row in rows[index+1:]+rows[:index+1]:
        if watched.get(key(row),(0,0))[0]<.95:return row
    return rows[0]  # A finished series can be started again explicitly.


def launch(row, context=None):
    if row is None:return 0
    if context:
        os.environ['NEWSBOAT_PLAYLIST_CONTEXT']=str(context)
        os.environ.pop('NEWSBOAT_QUEUE_PLAYBACK',None)
    else:os.environ.pop('NEWSBOAT_PLAYLIST_CONTEXT',None)
    path=Path(__file__).with_name('newsboat-play-video.py')
    spec=importlib.util.spec_from_file_location('resume_player',path)
    player=importlib.util.module_from_spec(spec);spec.loader.exec_module(player)
    return player.launch([row['url'],row.get('title','')])


def playthrough(url):
    import newsboat_playthroughs as library
    ident=url.split('://',1)[-1]
    group=next((group for group in library.read_groups() if group['id']==ident),None)
    if group is None:raise ValueError('Playthrough is no longer available')
    return launch(playlist_row(group['rows']),library.directory()/(ident+'.json'))
