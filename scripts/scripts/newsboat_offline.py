"""Browse cached Downloads and Playthroughs without the feed server."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import shlex
import xml.etree.ElementTree as ET
import subprocess
import tempfile
from newsboat_sources import feed_titles


def prepare(directory, config, urls, cache):
    root = Path(directory)
    offline_cache = root/'cache.db'
    with closing(sqlite3.connect(cache.as_uri()+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(offline_cache)) as target:
        source.backup(target)
        target.executemany('UPDATE rss_feed SET title=? WHERE rssurl=?',
                           [(title, feed) for feed, title in feed_titles().items()])
        target.commit()
        feeds = [row[0] for row in source.execute('SELECT rssurl FROM rss_feed')
                 if not row[0].startswith('query:')]
    downloads = next((line for line in urls.read_text().splitlines()
                      if line.startswith('"query:📥 Downloads:')), '"query:📥 Downloads:link = \\\"\\\""')
    # Import a local catalog only; the original subscriptions are never refreshed.
    from newsboat_playthroughs import groups, TITLE
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, value in [('title', TITLE), ('link', 'newsboat-playthroughs://home'),
                       ('description', 'Saved playlists')]:
        ET.SubElement(channel, key).text = value
    for group in groups():
        item = ET.SubElement(channel, 'item')
        for key, value in [('title', group['name']+' — '+group['channel']),
                           ('link', 'newsboat-playthroughs://'+group['id']),
                           ('guid', 'offline-playthrough:'+group['id'])]:
            ET.SubElement(item, key).text = value
    catalog = root/'playthroughs.xml'
    ET.ElementTree(rss).write(catalog, encoding='utf-8', xml_declaration=True)
    import_urls = root/'import-urls'
    import_urls.write_text(catalog.as_uri()+'\n')
    import_config = root/'import-config'
    import_config.write_text('urls-source local\n')
    binary = Path.home()/'.local/lib/newsboat-paged/newsboat'
    executable = str(binary) if binary.exists() else 'newsboat'
    subprocess.run([executable, '-q', '-C', str(import_config), '-u', str(import_urls),
                    '-c', str(offline_cache), '-x', 'reload'], check=True,
                   capture_output=True, timeout=15)
    playthroughs = json.dumps('query:'+TITLE+':link =~ "^newsboat-playthroughs://"', ensure_ascii=False)
    offline_urls = root/'urls'
    offline_urls.write_text(downloads+'\n'+playthroughs+'\n'+catalog.as_uri()+'\n'+''.join(json.dumps(feed)+'\n' for feed in feeds))
    action = shlex.quote(sys.executable)+' '+shlex.quote(str(Path(__file__).resolve()))+' open %u'
    offline_config = root/'config'
    lines = [
        'include '+json.dumps(str(config)),
        'urls-source local', 'auto-reload no', 'show-read-feeds yes', 'show-read-articles yes',
        'prepopulate-query-feeds yes',
        'run-on-startup set-filter '+json.dumps('rssurl =~ "^query:"'),
        'feedlist-title-format " 🚢 Newsboat — offline"',
        'articlelist-title-format " %T — offline"',
        'bind R everywhere redraw -- "Offline: restart Newsboat to reconnect"',
        'bind r feedlist,articlelist redraw -- "Offline: restart Newsboat to reconnect"',
        'bind q articlelist quit -- "Back to offline home"',
    ]
    for key in ('<ENTER>', 'o', 'O'):
        lines.append(f'bind {key} articlelist,searchresultslist set browser '+json.dumps(action)+' ; open-in-browser -- "Open saved item"')
    offline_config.write_text('\n'.join(lines)+'\n')
    env = dict(os.environ)
    for key in ('NEWSBOAT_LIVE_QUERIES', 'NEWSBOAT_NESTED_VIEWS', 'NEWSBOAT_UNDO_HELPER', 'NEWSBOAT_UNDO_FILE', 'NEWSBOAT_SYNC_VIEW', 'NEWSBOAT_GLOBAL_SEARCH_REQUEST'):
        env.pop(key, None)
    env['NEWSBOAT_URLS_FILE'] = str(offline_urls)
    return [executable, '-q', '-C', str(offline_config), '-u', str(offline_urls), '-c', str(offline_cache)], env


def show(config, urls, cache):
    with tempfile.TemporaryDirectory(prefix='newsboat-offline-') as directory:
        command, env = prepare(directory, config, urls, cache)
        return subprocess.call(command, env=env)


if __name__ == '__main__':
    url = sys.argv[2]
    scripts = Path(__file__).resolve().parent
    if url.startswith('newsboat-playthroughs://'):
        raise SystemExit(subprocess.call([sys.executable, str(scripts/'newsboat-playthroughs.py'), 'group', url]))
    subprocess.Popen([sys.executable, str(scripts/'newsboat-open.py'), url],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
