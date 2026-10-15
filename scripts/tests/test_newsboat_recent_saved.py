import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import newsboat_saved_dates as dates
from test_newsboat_reconnect import reader,pyte,BINARY

class SavedDateTests(unittest.TestCase):
    def test_initial_unknown_remote_new_and_undo(self):
        with tempfile.TemporaryDirectory() as d:
            status=Path(d)/'stars'
            with patch.object(dates.time,'time',return_value=2000000000):
                self.assertEqual(dates.sync(status,[{'url':'old'}]),{'old':2000000000})
                dates.record(status,'new',True)
                self.assertEqual(dates.sync(status,[{'url':'old'},{'url':'new'}])['new'],2000000000)
            with patch.object(dates.time,'time',return_value=2000000100):
                dates.record(status,'new',True) # repeated s must not reset age
                self.assertEqual(dates.sync(status,[{'url':'new'},{'url':'phone'}])['new'],2000000000)
                self.assertEqual(dates.sync(status,[{'url':'new'},{'url':'phone'}])['phone'],2000000100)
                dates.record(status,'new',False)
                dates.sync(status,[{'url':'phone'}])
                dates.record(status,'new',True,restore=True)
                self.assertEqual(dates.sync(status,[{'url':'new'}])['new'],2000000000)
                dates.record(status,'new',False);dates.record(status,'new',True)
                self.assertEqual(dates.sync(status,[{'url':'new'}])['new'],2000000100)

    def test_legacy_grace_does_not_reset_or_replace_known_dates(self):
        with tempfile.TemporaryDirectory() as d:
            status=Path(d)/'stars'
            with dates.database(status) as db:
                db.executemany('INSERT INTO stars VALUES(?,?,1)', [('unknown',0),('known',1000000000)])
                db.execute("INSERT INTO meta VALUES('initialized')")
            rows=[{'url':'unknown'},{'url':'known'}]
            with patch.object(dates.time,'time',return_value=2000000000):
                self.assertEqual(dates.sync(status,rows),{'unknown':2000000000,'known':1000000000})
            with patch.object(dates.time,'time',return_value=2002000000):
                self.assertEqual(dates.sync(status,rows),{'unknown':2000000000,'known':1000000000})
            with dates.database(status) as db:
                self.assertEqual(db.execute("SELECT saved FROM stars WHERE url='unknown'").fetchone()[0],0)

class DownloadDatesTests(unittest.TestCase):
    def test_saved_date_is_download_time_and_does_not_change_on_refresh(self):
        import newsboat_download_status as status
        with tempfile.TemporaryDirectory() as d,patch('newsboat_storage.publish'):
            root=Path(d);state=root/'downloads';state.mkdir()
            file=root/'article.html';file.write_text('article')
            url='https://example.com/article'
            (state/'job.json').write_text(json.dumps(dict(url=url,status='done',updated=1234567890,files=[str(file)])))
            with patch.dict('os.environ',{'NEWSBOAT_CACHE':str(root/'missing.db')}):
                status.publish(state)
                self.assertEqual((root/'download-status.tsv.saved').read_text(),url+'\t1234567890.0\n')
                status.publish(state)
                self.assertEqual((root/'download-status.tsv.saved').read_text(),url+'\t1234567890.0\n')

@unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
class NativeRecentTests(unittest.TestCase):
    def test_recent_default_toggle_and_home_count(self):
        for kind in ('starred','downloads'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);now=time.time();a='https://example.com/recent';b='https://example.com/older'
                stars=root/'stars';stars.write_text(a+'\n'+b+'\n');Path(str(stars)+'.saved').write_text(f'{a}\t{now}\n{b}\t{now-20*86400}\n')
                status=root/'downloads';status.write_text(f'{a}\t📥\n{b}\t📥\n');Path(str(status)+'.saved').write_text(Path(str(stars)+'.saved').read_text())
                title='⭐ Starred' if kind=='starred' else '📥 Downloads'
                feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description>'+''.join(f'<item><title>{name}</title><link>{url}</link><guid>{name}</guid><pubDate>{pub}</pubDate></item>' for name,url,pub in [('Recent save',a,'Sat, 01 Jan 2000 12:00:00 GMT'),('Older save',b,'Tue, 13 Oct 2026 12:00:00 GMT')])+'</channel></rss>')
                urls=json.dumps('query:'+title+':title =~ "save"',ensure_ascii=False)+'\n'+feed.as_uri()+'\n'
                cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nprepopulate-query-feeds yes\nfeedlist-format "%t %v"\narticlelist-title-format "%T count=%t"\nbind l articlelist toggle-show-read-feeds\nrun-on-startup set-filter '+json.dumps('rssurl =~ "^query:"')+'\n'
                with reader(root,cfg,urls,{'NEWSBOAT_STARRED_STATUS':str(stars),'NEWSBOAT_DOWNLOAD_STATUS':str(status)}) as (_,screen,send,wait):
                    wait(lambda s:title+' 1' in s)
                    send('\n');wait(lambda s:'Recent save' in s and 'Older save' not in s)
                    send('l');wait(lambda s:'Recent save' in s and 'Older save' in s)
                    send('l');wait(lambda s:'Recent save' in s and 'Older save' not in s)
                    send('q');wait(lambda s:title+' 1' in s)
                    send('\n');wait(lambda s:'Recent save' in s and 'Older save' not in s)
                    datefile=Path(str(stars if kind=='starred' else status)+'.saved')
                    datefile.write_text(f'{a}\t{now-20*86400}\n{b}\t{now-20*86400}\n')
                    wait(lambda s:'Recent save' not in s and 'Older save' not in s)
                    send('l');wait(lambda s:'Recent save' in s and 'Older save' in s)
                    send('q');wait(lambda s:title+' 0' in s)
