"""Open cached Downloads without connecting to the feed server."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile


def prepare(directory, config, urls, cache):
    root = Path(directory)
    offline_cache = root/'cache.db'
    with closing(sqlite3.connect(cache.as_uri()+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(offline_cache)) as target:
        source.backup(target)
        feeds = [row[0] for row in source.execute('SELECT rssurl FROM rss_feed')
                 if not row[0].startswith('query:')]
    downloads = next((line for line in urls.read_text().splitlines()
                      if line.startswith('"query:📥 Downloads:')), '"query:📥 Downloads:link = \\\"\\\""')
    offline_urls = root/'urls'
    offline_urls.write_text(downloads+'\n'+''.join(json.dumps(feed)+'\n' for feed in feeds))
    offline_config = root/'config'
    offline_config.write_text(
        f'include {json.dumps(str(config))}\n'
        'urls-source local\nauto-reload no\nshow-read-feeds yes\nshow-read-articles yes\n'
        'prepopulate-query-feeds yes\nrun-on-startup open\n'
        'articlelist-title-format "📥 Downloads — offline"\n'
        'bind R everywhere redraw -- "Offline: restart Newsboat to reconnect"\n'
        'bind r feedlist,articlelist redraw -- "Offline: restart Newsboat to reconnect"\n'
        'bind q articlelist hard-quit -- "Close offline Downloads"\n')
    env = dict(os.environ)
    for key in ('NEWSBOAT_LIVE_QUERIES', 'NEWSBOAT_NESTED_VIEWS', 'NEWSBOAT_UNDO_HELPER', 'NEWSBOAT_UNDO_FILE', 'NEWSBOAT_SYNC_VIEW'):
        env.pop(key, None)
    env['NEWSBOAT_URLS_FILE'] = str(offline_urls)
    return ['newsboat', '-q', '-C', str(offline_config), '-u', str(offline_urls), '-c', str(offline_cache)], env


def show(config, urls, cache):
    with tempfile.TemporaryDirectory(prefix='newsboat-offline-') as directory:
        command, env = prepare(directory, config, urls, cache)
        return subprocess.call(command, env=env)
