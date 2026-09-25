#!/usr/bin/env python3
"""Refresh the Starred menu and safely maintain the download library."""
import importlib.util
import json
import sys
from pathlib import Path
from newsboat_miniflux import Client
import newsboat_download_cleanup as cleanup
from urllib.parse import urlparse


def publish_feed_platforms(client):
    from newsboat_media import atomic_write
    lines = []
    titles = {}
    for feed in client.request('feeds'):
        titles[str(feed['id'])] = feed['title']
        hosts = {urlparse(feed.get(key, '')).hostname for key in ('feed_url', 'site_url')}
        icon = ' ' if hosts & {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'} else ' ' if hosts & {'twitch.tv', 'www.twitch.tv', 'twitchrss.appspot.com'} else ''
        if icon:
            lines.append(f'{feed["id"]}\t{icon}\n')
    atomic_write(cleanup.STATE/'download-status.tsv.feeds', ''.join(lines))
    atomic_write(cleanup.STATE/'feed-titles.json', json.dumps(titles, ensure_ascii=False))


def load_starred():
    spec = importlib.util.spec_from_file_location('newsboat_starred', Path(__file__).with_name('newsboat-starred.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if sys.argv[1:2] == ['resume']:
        from newsboat_watch_progress import resume_position
        print(resume_position(sys.argv[2],float(sys.argv[3]) if len(sys.argv)>3 else 0))
        return 0
    if sys.argv[1:2] == ['progress']:
        from newsboat_watch_progress import record
        return 0 if record(sys.argv[2], float(sys.argv[3]), float(sys.argv[4])) else 1
    if sys.argv[1:2] == ['watched']:
        return 0 if cleanup.record(sys.argv[2],sys.argv[3],float(sys.argv[4])) else 1
    starred = load_starred()
    try:
        client = Client()
        publish_feed_platforms(client)
        rows = client.starred()
        starred.rebuild_query(rows)
        if sys.argv[1:2] != ['sync'] and cleanup.CONFIG.exists():
            settings = json.loads(cleanup.CONFIG.read_text())
            if settings.get('enabled'):
                removed = cleanup.cleanup([row['url'] for row in rows], settings['days'])
                if removed:
                    print(f'Removed {len(removed)} watched downloads')
        return 0
    except Exception:
        # An outage must never trigger unprotected cleanup.
        print('Miniflux unavailable; cleanup was skipped.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
