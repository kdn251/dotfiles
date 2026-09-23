import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('commentary',SCRIPTS/'newsboat-commentary.py')
commentary=importlib.util.module_from_spec(spec);spec.loader.exec_module(commentary)

class CommentaryTests(unittest.TestCase):
    def test_save_persistence_count_order_remove_and_native_config(self):
        import sys
        sys.path.insert(0,str(SCRIPTS))
        import newsboat_media
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); cache=root/'cache';urls=root/'urls';state=root/'state'
            urls.write_text('\n'.join(json.dumps('query:'+name+':link = "none"',ensure_ascii=False) for name in ['📬 New','⭐ Starred','📥 Downloads','🌎 All'])+'\n')
            with sqlite3.connect(cache) as db:
                db.execute('CREATE TABLE rss_feed(rssurl TEXT,title TEXT)')
                db.execute('CREATE TABLE rss_item(id INTEGER,url TEXT,title TEXT,feedurl TEXT,content TEXT)')
                db.execute('INSERT INTO rss_feed VALUES ("1","Source")')
                db.execute('INSERT INTO rss_item VALUES (1,"https://example.com/article","Saved title","1","Full content")')
            with patch.multiple(commentary,CACHE=cache,URLS=urls,STATE=state), patch.object(newsboat_media,'STATE',state/'downloads'):
                commentary.save('https://example.com/article');commentary.save('https://example.com/article')
                self.assertEqual(len(commentary.entries()),1)
                self.assertEqual((state/'starred-urls.txt.commentary.count').read_text(),'1\n')
                self.assertEqual((state/'starred-urls.txt.commentary').read_text(),'https://example.com/article\n')
                text=urls.read_text();self.assertLess(text.index('📣 Commentary'),text.index('🌎 All'))
                with sqlite3.connect(cache) as db:db.execute('DELETE FROM rss_item')
                self.assertEqual(commentary.entries()[0][1],'Saved title')
                view=root/'view';view.mkdir();command,config=commentary.prepare_view(view)
                self.assertIn('delete-article ; purge-deleted',config.read_text())
                self.assertIn('Full content',(view/'history.xml').read_text())
                binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
                if binary.exists():
                    command[0]=str(binary)
                    result=subprocess.run(command+['-x','reload'],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                commentary.remove('https://example.com/article')
                self.assertEqual(commentary.entries(),[])
                self.assertEqual((state/'starred-urls.txt.commentary.count').read_text(),'0\n')
                self.assertEqual((state/'starred-urls.txt.commentary').read_text(),'')
                commentary.restore('https://example.com/article', True)
                restored = commentary.entries()[0]
                self.assertEqual(restored[1], 'Saved title')
                self.assertEqual(restored[3], 'Full content')
                commentary.restore('https://example.com/article', False)
                self.assertEqual(commentary.entries(), [])
