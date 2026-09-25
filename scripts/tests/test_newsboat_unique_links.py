"""Duplicate destinations stay unique, including after marking read and undo."""
import sqlite3,tempfile,unittest
from pathlib import Path
from test_newsboat_reconnect import reader,pyte,BINARY

@unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
class UniqueLinksTests(unittest.TestCase):
    def test_query_read_undo_and_search(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('one','two'):
                (root/name).write_text('<rss version="2.0"><channel><title>'+name+'</title><link>https://example.org</link><description>test</description><item><title>Goodbye Google</title><guid>'+name+'</guid><link>https://example.org/shared</link></item>'+('<item><title>Goodbye Google different article</title><guid>other</guid><link>https://example.org/other</link></item>' if name=='two' else '')+'</channel></rss>')
            urls='"query:📬 New:unread = \\"yes\\""\n"query:🌎 All:unread = \\"yes\\""\n'+''.join((root/n).as_uri()+'\n' for n in ('one','two'))
            cfg='auto-reload no\nsuppress-first-reload yes\nshow-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nconfirm-exit no\nfeedlist-format "%t %v"\narticle-sort-order title-asc\nbind n articlelist toggle-article-read\nbind U everywhere undo-action\n'
            with reader(root,cfg,urls,dict(NEWSBOAT_UNDO_FILE=str(root/'undo'))) as (_,screen,send,wait):
                wait(lambda s:'New 2' in s and 'All 2' in s)
                send('\n');wait(lambda s:'Goodbye Google different article' in s)
                self.assertEqual('\n'.join(screen.display).count('Goodbye Google'),2)
                send('n')
                def unread():
                    with sqlite3.connect(root/'cache') as db:return db.execute("select sum(unread) from rss_item where url='https://example.org/shared'").fetchone()[0]
                wait(lambda s:unread()==0)
                send('q');wait(lambda s:'New 1' in s and 'All 1' in s)
                send('U');wait(lambda s:unread()==2 and 'New 2' in s)
                send('/Goodbye\n');wait(lambda s:'Search' in screen.display[0] and 'Goodbye Google different article' in s)
                self.assertEqual('\n'.join(screen.display).count('Goodbye Google'),2)

class StarredUniqueTests(unittest.TestCase):
    def test_display_and_count_unique_but_keep_remote_ids(self):
        import importlib.util,json,xml.etree.ElementTree as ET
        from unittest.mock import patch
        path=Path(__file__).resolve().parents[1]/'scripts/newsboat-starred.py'
        spec=importlib.util.spec_from_file_location('starred_unique',path)
        starred=importlib.util.module_from_spec(spec);spec.loader.exec_module(starred)
        rows=[dict(id=i,url='https://example.org/shared',title='Same article',feed=dict(title='Source'),published_at='2026-09-01T00:00:00Z') for i in (1,2)]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(starred,'STARRED_STATUS',root/'starred-urls.txt'):
                starred.rebuild_query(rows)
                self.assertEqual((root/'starred-urls.txt.count').read_text().strip(),'1')
                self.assertEqual(len(json.loads((root/'starred-items.json').read_text())),2)
            starred.write_feed(root,rows)
            self.assertEqual(len(ET.parse(root/'history.xml').findall('./channel/item')),1)
