"""Local native-messaging bridge for explicitly registered Newsboat articles."""
from contextlib import closing
import json
import re
import struct
import sys
from urllib.parse import urlsplit, urlunsplit

from newsboat_articles import canonical, key
import newsboat_reading as reading


def normalized(url):
    url = canonical(url)
    url = re.sub(r'^(https?://)(?:www\.|np\.|new\.|old\.)?reddit\.com/',
                 r'\1reddit.com/', url)
    parts = urlsplit(url)
    # Feed URLs often predate HTTPS or redirect between www and the bare host.
    # Keep the path/query and explicit ports distinct; never match by title.
    host = parts.netloc.lower().removeprefix('www.')
    return urlunsplit(('https', host, parts.path or '/', parts.query, ''))


def database():
    db = reading.database()
    db.execute("CREATE TABLE IF NOT EXISTS browser_articles (url TEXT PRIMARY KEY, id TEXT NOT NULL, position TEXT DEFAULT '{}')")
    return db


def register(url):
    url = canonical(url)
    ident = key(url)
    with closing(database()) as db, db:
        if any(normalized(existing) == normalized(url)
               for (existing,) in db.execute('SELECT url FROM browser_articles')):
            return
        db.execute('INSERT OR IGNORE INTO articles(id,url) VALUES (?,?)', (ident, url))
        db.execute('INSERT OR IGNORE INTO browser_articles(url,id) VALUES (?,?)', (normalized(url), ident))


def handle(message):
    url = normalized(message['url'])
    with closing(database()) as db:
        row = db.execute('SELECT id,position,url FROM browser_articles WHERE url=?', (url,)).fetchone()
        if not row:
            # Existing registrations used their original HTTP/www spelling.
            # Retain their ID so progress still appears on the original feed URL.
            row = next((entry for entry in db.execute('SELECT id,position,url FROM browser_articles')
                        if normalized(entry[2]) == url), None)
    if not row:
        return {'tracked': False}
    ident, position, stored_url = row
    if message.get('action') == 'save':
        data = message['position']
        # Shared percentage, separate anchors: the original DOM and saved reader
        # have different layouts. Never overwrite the downloaded reader's anchor.
        text = data.get('text', '')
        if not isinstance(text, str) or len(text) > 240:
            raise ValueError('Invalid anchor text')
        reading.record(ident, data, save_position=False)
        position = json.dumps({k: data[k] for k in ('y','anchor','offset','text') if k in data})
        with closing(database()) as db, db:
            db.execute('UPDATE browser_articles SET position=? WHERE url=?', (position, stored_url))
    elif message.get('action') != 'get':
        raise ValueError('Unknown action')
    return {'tracked': True, 'fraction': reading.lookup(ident)[1], 'position': json.loads(position)}


def serve():
    while True:
        header = sys.stdin.buffer.read(4)
        if not header:
            return
        if len(header) != 4:
            return
        length, = struct.unpack('=I', header)
        if not 0 < length <= 8192:
            return
        data = sys.stdin.buffer.read(length)
        if len(data) != length:
            return
        try:
            result = handle(json.loads(data))
        except (ValueError, TypeError, KeyError, AttributeError):
            result = {'tracked': False, 'error': 'Invalid reading data'}
        output = json.dumps(result).encode()
        sys.stdout.buffer.write(struct.pack('=I', len(output)) + output)
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    serve()
