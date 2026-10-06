"""Persistent autoplay preference and completed Downloads candidates for mpv."""
import json
import os
from pathlib import Path
import random
import sys
import newsboat_media as media


def preference():
    return Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/autoplay.json'


def enabled():
    try:
        return json.loads(preference().read_text()).get('enabled', True) is True
    except (OSError, ValueError):
        return True


def download_candidates(current):
    from newsboat_playthroughs import member_keys
    excluded = member_keys() | {media.identity(current)}
    try:
        index = json.loads((media.STATE/'.media-index.json').read_text())
    except (OSError, ValueError):
        return []
    found = {}
    for filename, entry in index.items():
        path = Path(filename)
        key = media.filename_identity(path)
        if (not entry.get('valid') or not key or key in excluded or not path.is_file()
                or not path.is_relative_to(media.ROOT) or path.parent == media.ROOT/'twitch-vods'):
            continue
        platform, ident = key
        url = ('https://www.youtube.com/watch?v='+ident if platform == 'youtube'
               else 'https://www.twitch.tv/videos/'+ident if platform == 'twitch' else '')
        if url:
            found[key] = dict(url=url, title=path.stem)
    return list(found.values())


def normal_plan(current):
    result = dict(enabled=enabled(), playlist=False, next=None, previous=None)
    try:
        data = json.loads(Path(os.environ.get('NEWSBOAT_PLAYLIST_CONTEXT', '')).read_text())
        rows = [row for row in data['rows'] if media.identity(row.get('url', ''))]
        index = next(i for i, row in enumerate(rows) if media.identity(row['url']) == media.identity(current))
        result.update(playlist=True, next=rows[index+1] if index+1<len(rows) else None,
                      previous=rows[index-1] if index else None)
        return result
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        pass
    candidates = download_candidates(current)
    if candidates:
        result['next'] = random.choice(candidates)
        result['next']['title'] = media.cached_title(result['next']['url']) or result['next']['title']
    return result


def plan(current):
    from newsboat_queue import entries, identity, navigation
    rows = entries()
    candidates = [row for row in rows if identity(row['url']) != identity(current)]
    queued = any(identity(row['url']) == identity(current) for row in rows)
    queue_playback = queued or os.environ.get('NEWSBOAT_QUEUE_PLAYBACK') == '1'
    if queue_playback:
        following, previous, manual_next = navigation(current)
        result = dict(enabled=enabled(), playlist=False, queue=True,
                      next=following or (candidates[0] if candidates else None),
                      previous=previous, queue_next=manual_next)
        if result['next'] is None:result['next']=normal_plan(current)['next']
        result['current_queue_token']=next((row['queue_token'] for row in rows if identity(row['url'])==identity(current)), '')
        return result

    # Preserve previous-episode navigation, but the queue owns next-video choice.
    if candidates:
        result = dict(enabled=enabled(), playlist=False, next=candidates[0], previous=None)
        try:
            data = json.loads(Path(os.environ.get('NEWSBOAT_PLAYLIST_CONTEXT', '')).read_text())
            index = next(i for i,row in enumerate(data['rows']) if identity(row['url']) == identity(current))
            result.update(playlist=True, previous=data['rows'][index-1] if index else None)
        except (OSError, ValueError, KeyError, StopIteration, TypeError):pass
    else:
        result = normal_plan(current)
    result['current_queue_token'] = next((row['queue_token'] for row in rows if identity(row['url']) == identity(current)), '')
    return result


if __name__ == '__main__':
    if sys.argv[1] == 'set':
        media.atomic_write(preference(), json.dumps(dict(enabled=sys.argv[2]=='on')))
    else:
        if len(sys.argv)>3:os.environ['NEWSBOAT_QUEUE_PLAYBACK']='1' if sys.argv[3]=='on' else '0'
        print(json.dumps(plan(sys.argv[2])))
