"""Compare playlist visits without treating downloads or metadata fetches as visits."""
import json
from pathlib import Path
import newsboat_youtube_playlists as library
from newsboat_media import atomic_write, identity
from newsboat_playthroughs import playlist_id


def keys(rows):
    return {':'.join(key) for row in rows if (key := identity(row.get('url', '')))}


def path(url):
    return library.LIBRARY/'playlist-visits'/(playlist_id(url)+'.json')


def previous(url, fallback=None):
    try:
        data=json.loads(path(url).read_text())
        return set(data['videos'])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if fallback is not None:
        return keys(fallback)
    # Migrate an existing browsed playlist without labeling its whole catalog new.
    try:
        data=json.loads((library.LIBRARY/'browsed-playlists'/(playlist_id(url)+'.json')).read_text())
        return keys(data['rows'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def additions(rows, before):
    if before is None:
        return []  # A first visit establishes the baseline.
    return [row['url'] for row in rows
            if (key := identity(row.get('url', ''))) and ':'.join(key) not in before]


def remember(url, rows):
    atomic_write(path(url), json.dumps({'videos':sorted(keys(rows))}))


def suffix(new_urls):
    count=len(set(new_urls))
    return f' · {count} new since last visit' if count else ''
