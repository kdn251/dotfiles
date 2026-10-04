#!/usr/bin/env python3
"""Reset progress and resume anchors without changing read/star/download state."""
from contextlib import closing
import sys
import time
import newsboat_media as media


def reset(url):
    identity = media.identity(url)
    if identity:
        import newsboat_watch_progress as watch
        import newsboat_download_cleanup as cleanup
        # A stored zero overrides mpv's own watch-later position on next open.
        watch.record(url, 0, 1)
        with media.library_lock(), closing(cleanup.database()) as db, db:
            paths = [path for path, stored in db.execute('SELECT path,url FROM watched')
                     if media.identity(stored) == identity]
            db.executemany('DELETE FROM watched WHERE path=?', [(path,) for path in paths])
    else:
        import newsboat_browser_reading as browser
        import newsboat_reading as reading
        normalized = browser.normalized(url)
        with reading.LOCK, closing(browser.database()) as db, db:
            ids = {ident for ident, stored in db.execute('SELECT id,url FROM articles')
                   if browser.normalized(stored) == normalized}
            ids.update(ident for stored, ident in db.execute('SELECT url,id FROM browser_articles')
                       if browser.normalized(stored) == normalized)
            for ident in ids:
                db.execute("UPDATE articles SET fraction=0,position='{}',updated=? WHERE id=?", (time.time(), ident))
                db.execute("UPDATE browser_articles SET position='{}' WHERE id=?", (ident,))
            db.commit()
            rows = db.execute('SELECT url,fraction FROM articles').fetchall()
            media.atomic_write(reading.STATE/'download-status.tsv.read',
                               ''.join(f'{link}\t{min(100,int(fraction*100))}%\n' for link,fraction in rows))


if __name__ == '__main__':
    reset(sys.argv[1])
