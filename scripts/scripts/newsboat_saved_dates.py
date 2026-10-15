"""Durable star save dates, separate from publication/read-state timestamps."""
import sqlite3
import time
from contextlib import contextmanager, closing
from pathlib import Path
from newsboat_media import atomic_write

@contextmanager
def database(status):
    path=Path(status).parent/'starred-saved-dates.db';path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path,timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS stars(url TEXT PRIMARY KEY,saved REAL,active INTEGER)')
        db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS legacy_grace(url TEXT PRIMARY KEY,started REAL)')
        yield db

def record(status,url,desired,restore=False):
    with database(status) as db:
        row=db.execute('SELECT saved,active FROM stars WHERE url=?',(url,)).fetchone()
        saved=row[0] if row and (restore or row[1] or not desired) else time.time() if desired else 0
        db.execute('INSERT OR REPLACE INTO stars VALUES(?,?,?)',(url,saved,int(desired)))

def sync(status,rows):
    urls={r['url'] for r in rows}
    with database(status) as db:
        initialized=db.execute('SELECT 1 FROM meta').fetchone() is not None
        old=dict((u,(s,a)) for u,s,a in db.execute('SELECT url,saved,active FROM stars'))
        now=time.time()
        for url in urls:
            prior=old.get(url)
            saved=prior[0] if prior and prior[1] else now if initialized else 0
            db.execute('INSERT OR REPLACE INTO stars VALUES(?,?,1)',(url,saved))
        for url in old.keys()-urls:db.execute('UPDATE stars SET active=0 WHERE url=?',(url,))
        db.execute("INSERT OR IGNORE INTO meta VALUES('initialized')")
        # Unknown legacy dates stay unknown; a separate, one-time grace period
        # prevents the migration from hiding the entire existing collection.
        db.execute('INSERT OR IGNORE INTO legacy_grace SELECT url,? FROM stars WHERE saved=0 AND active=1',(now,))
        saved=dict(db.execute('SELECT s.url,CASE WHEN s.saved>0 THEN s.saved ELSE g.started END FROM stars s LEFT JOIN legacy_grace g ON g.url=s.url WHERE s.active=1'))
        # Publish while holding the write transaction so concurrent workers
        # cannot replace a newer snapshot with an older one.
        atomic_write(Path(str(status)+'.saved'),''.join(f'{url}\t{stamp}\n' for url,stamp in sorted(saved.items()) if not any(c in url for c in '\t\r\n')))
    return saved
