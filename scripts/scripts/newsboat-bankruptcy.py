#!/usr/bin/env python3
"""Explicitly confirmed Downloads cleanup; saved playlists are always protected."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
import newsboat_media as media
import newsboat_playthroughs as playlists
import newsboat_queue as queue


def protected_keys():
    # Read strictly: corrupted playlist metadata must abort, never silently hide
    # a playlist from the preservation set. Preserve every catalog member.
    protected=set()
    for path in playlists.directory().glob('*.json'):
        group=json.loads(path.read_text())
        for url in group.get('selected_urls',[]):protected.add(media.identity(url))
        for row in group.get('rows',[]):protected.add(media.identity(row['url']))
    for path in (media.ROOT/'twitch-vods').glob('*'):
        if path.is_file():protected.add(media.filename_identity(path))
    return protected


def targets():
    protected=protected_keys()
    urls={}
    for _,job in media.records():
        key=media.library_identity(job['url'])
        if key and key not in protected and job.get('status')!='deleted':urls[key]=job['url']
    bases={'youtube':'https://www.youtube.com/watch?v=', 'twitch':'https://www.twitch.tv/videos/',
           'twitch-clip':'https://clips.twitch.tv/'}
    for key,path in media.candidates():
        if path.is_relative_to(media.ROOT) and key not in protected and key[0] in bases:
            urls[key]=bases[key[0]]+key[1]
    return list(urls.values())


def execute():
    media.STATE.parent.mkdir(parents=True,exist_ok=True)
    with (media.STATE.parent/'bankruptcy.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Downloads cleanup is already running')
        urls=targets()  # Validate protection before changing anything.
        failures=[];removed=0
        for url in urls:
            key=media.library_identity(url)
            if key in protected_keys():continue
            # Cancel ordinary workers before removal; never signal playlist jobs.
            active=any(media.library_identity(j['url'])==key and j.get('status') in
                       {'preparing','downloading','processing','retrying','waiting'} for _,j in media.records())
            if active:
                subprocess.run([sys.executable,str(Path(__file__).with_name('newsboat-download.py')),
                                '--cancel-url',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+8
            while True:
                try:
                    removed+=media.delete(url,refresh=False,protect=lambda key:key in protected_keys())
                    break
                except ValueError as error:
                    if active and time.monotonic()<deadline:time.sleep(.2);continue
                    failures.append(str(error));break
                except OSError as error:
                    failures.append(str(error));break
        queue.change('clear')
        media.rebuild()
        return removed,failures


def main():
    if sys.argv[1:]!=['--confirmed']:
        print('Use Shift+B on the Newsboat home screen and confirm.',file=sys.stderr)
        return 2
    try:
        removed,failures=execute()
        message=f'Deleted {removed} downloaded files; Queue cleared. Playlists and VODs kept.'
        if failures:message+=f' {len(failures)} downloads could not be deleted; retry after they stop.'
        subprocess.run(['notify-send','-a','Newsboat','-t','6000','Downloads cleared' if not failures else 'Cleanup partially completed',message])
        return bool(failures)
    except (OSError,ValueError,KeyError) as error:
        subprocess.run(['notify-send','-a','Newsboat','-t','6000','Cleanup stopped',str(error)])
        return 1

if __name__=='__main__':sys.exit(main())
