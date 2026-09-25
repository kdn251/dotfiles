"""Article extraction, offline assets, library lifecycle, and browser routing."""
import base64
import functools
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import newsboat_articles as articles
import newsboat_media as media

PYTHON=Path.home()/'.local/share/newsboat/article-venv/bin/python'
TEXT='A small home server can provide a useful place to store photographs and documents. Backups should be tested regularly to ensure that important files remain recoverable. '
PAGE='<html><head><title>Offline test article</title><meta name="author" content="Test Author"></head><body><article><h1>Offline test article</h1>'+''.join(f'<p>Section {i}. {TEXT}</p>' for i in range(6))+'<img src="/image.png"><a href="/related">Related article</a><script>alert(1)</script></article></body></html>'

@unittest.skipUnless(PYTHON.exists(),'install newsboat-article-setup.sh first')
class ArticleTests(unittest.TestCase):
    def test_download_library_open_delete_and_no_external_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'article.html').write_text(PAGE)
            (root/'image.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aJ1sAAAAASUVORK5CYII='))
            class Handler(http.server.SimpleHTTPRequestHandler):
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=directory))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            url=f'http://127.0.0.1:{server.server_port}/article.html'
            fakebin=root/'bin';fakebin.mkdir()
            (fakebin/'notify-send').write_text('#!/bin/sh\necho 1\n');(fakebin/'notify-send').chmod(0o755)
            (fakebin/'brave').write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$OPENED"\n');(fakebin/'brave').chmod(0o755)
            env=dict(os.environ,NEWSBOAT_VIDEO_DIR=str(root/'library'),XDG_STATE_HOME=str(root/'state'),
                     NEWSBOAT_URLS_FILE=str(root/'urls'),NEWSBOAT_CACHE=str(root/'cache'),
                     OPENED=str(root/'opened'),PATH=str(fakebin)+':'+os.environ['PATH'])
            try:
                subprocess.run([sys.executable,str(SCRIPTS/'newsboat-download.py'),url],env=env,check=True,timeout=30)
            finally:
                server.shutdown();server.server_close()
            job=json.loads(next((root/'state/newsboat/downloads').glob('[!.]*.json')).read_text())
            self.assertEqual(job['status'],'done')
            saved=Path(job['files'][0]);page=saved.read_text()
            self.assertIn('data:image/png;base64,',page)
            self.assertNotIn('alert(1)',page)
            self.assertEqual(page.count('<script'),1)
            self.assertIn('Open original',page)
            self.assertIn('Test Author',page)
            self.assertIn(url,(root/'urls').read_text())
            self.assertIn(url+'\t📥',(root/'state/newsboat/download-status.tsv').read_text())
            # Server is stopped: opening must still select the saved file.
            subprocess.run([sys.executable,str(SCRIPTS/'newsboat-open.py'),url],env=env,check=True,timeout=10)
            opened=(root/'opened').read_text().strip()
            self.assertTrue(opened.startswith('--app=http://127.0.0.1:'))
            self.assertIn('/article/',opened)
            from urllib.request import urlopen
            with urlopen(opened.removeprefix('--app=')) as response:
                self.assertIn('Offline test article', response.read().decode())
            server=json.loads((root/'state/newsboat/article-server.json').read_text())
            import signal
            os.kill(server['pid'],signal.SIGTERM)
            subprocess.run([sys.executable,str(SCRIPTS/'newsboat_media.py'),'delete',url],env=env,check=True,timeout=15)
            self.assertFalse(saved.exists())
            self.assertNotIn(url,(root/'urls').read_text())
            self.assertNotIn(url,(root/'state/newsboat/download-status.tsv').read_text())

    def test_extraction_rejects_teasers_and_marks_missing_images(self):
        code='''import sys
sys.path.insert(0,sys.argv[1])
import newsboat_articles as a
page,title,warnings=a.render(sys.stdin.read(),'https://example.com/article',fetch_image=lambda *args: (_ for _ in ()).throw(OSError('offline')))
assert warnings and 'Image unavailable offline' in page
assert 'src="http' not in page and 'alert(1)' not in page
assert page.count('<script') == 1
try:a.render('<html><body><article><p>Subscribe to continue reading.</p></article></body></html>','https://example.com')
except ValueError:pass
else:raise AssertionError('Accepted teaser')
'''
        subprocess.run([str(PYTHON),'-c',code,str(SCRIPTS)],input=PAGE,text=True,check=True)

    def test_short_reddit_post_uses_cache_without_fetching_reddit(self):
        code = """import sys,sqlite3,tempfile,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import newsboat_articles as a
from unittest.mock import patch
with tempfile.TemporaryDirectory() as d:
    cache=Path(d)/'cache.db'
    with sqlite3.connect(cache) as db:
        db.execute('CREATE TABLE rss_item(id INTEGER,url TEXT,title TEXT,content TEXT)')
        db.execute('INSERT INTO rss_item VALUES (1,?,?,?)',('https://www.reddit.com/r/test/comments/abc123/example/','Short post','<p>A short but complete post.</p><script>alert(1)</script>'))
        db.execute('INSERT INTO rss_item VALUES (2,?,?,?)',('https://www.reddit.com/r/test/comments/cross1/example/','Crosspost','submitted by <a href="https://www.reddit.com/user/test">user</a><a href="https://www.reddit.com/r/test/comments/abc123/example/">[link]</a><a href="https://www.reddit.com/r/test/comments/cross1/example/">[comments]</a>'))
        db.execute('INSERT INTO rss_item VALUES (3,?,?,?)',('https://www.reddit.com/r/test/comments/empty1/example/','Empty','submitted by <a href="https://www.reddit.com/user/test">user</a><a href="https://www.reddit.com/r/test/comments/empty1/example/">[link]</a><a href="https://www.reddit.com/r/test/comments/empty1/example/">[comments]</a>'))
    with patch.dict(os.environ,NEWSBOAT_CACHE=str(cache)), patch.object(a,'fetch',side_effect=OSError('Blocked')):
        cross_title,cross_body=a.reddit_snapshot('https://www.reddit.com/r/test/comments/cross1/example/')
        assert cross_title=='Crosspost' and 'A short but complete post.' in cross_body
        try:a.reddit_snapshot('https://www.reddit.com/r/test/comments/empty1/example/')
        except ValueError:pass
        else:raise AssertionError('Saved feed boilerplate as post content')
        title,body=a.reddit_snapshot('https://old.reddit.com/r/test/comments/abc123/example/')
    page,title,warnings=a.render(body,'https://www.reddit.com/r/test/comments/abc123/example/',title,reddit=True,fetch_image=lambda *args: (_ for _ in ()).throw(AssertionError('Network request')))
    assert 'A short but complete post.' in page
    assert 'Saved post and comment snapshot' in page
    assert 'alert(1)' not in page
    assert a.keyboard_support(page)==page
    assert 'window.close()' in page
"""
        subprocess.run([str(PYTHON),'-c',code,str(SCRIPTS)],check=True)

    def test_reddit_comments_include_nested_replies_and_report_fetch_failure(self):
        def comment(author, text, replies=''):
            return {'kind':'t1','data':{'author':author,'body':text,'score':3,'replies':replies}}
        payload=[{}, {'data':{'children':[
            comment('parent','First comment',{'data':{'children':[comment('reply','A reply')]}}),
            {'kind':'more','data':{}}]}}]
        with patch.object(articles,'fetch',return_value=(json.dumps(payload).encode(),'application/json','https://reddit.com')):
            content,warnings=articles.reddit_comments('https://www.reddit.com/r/test/comments/abc123/title/')
        self.assertFalse(warnings)
        self.assertIn('Comments (2 saved)',content)
        self.assertIn('First comment',content)
        self.assertIn('A reply',content)
        self.assertIn('Some comments or replies were not included',content)
        with patch.object(articles,'fetch',side_effect=OSError('403')):
            content,warnings=articles.reddit_comments('https://www.reddit.com/r/test/comments/abc123/title/')
        self.assertEqual(warnings,['Reddit comments unavailable'])
        self.assertIn('could not be downloaded',content)

    def test_reddit_json_blocked_falls_back_to_comment_feed(self):
        rss='''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>t3_abc123</id><content type="html">&lt;p&gt;Post text&lt;/p&gt;</content></entry>
          <entry><id>t1_reply1</id><author><name>/u/Alice</name></author><link href="https://www.reddit.com/r/test/comments/abc123/title/reply1/"/><content type="html">&lt;p&gt;First comment with &lt;strong&gt;formatting&lt;/strong&gt;.&lt;/p&gt;</content></entry>
          <entry><id>t1_reply2</id><author><name>/u/Bob</name></author><link href="https://www.reddit.com/r/test/comments/abc123/title/reply2/"/><content type="html">&lt;p&gt;A reply &amp;amp; more text.&lt;/p&gt;</content></entry>
          <entry><id>t1_reply2</id><link href="https://www.reddit.com/r/test/comments/abc123/title/reply2/"/><content type="html">Duplicate</content></entry>
          <entry><id>t1_wrong</id><link href="https://www.reddit.com/r/test/comments/other1/title/wrong/"/><content type="html">Wrong thread</content></entry>
        </feed>'''
        with patch.object(articles,'fetch',side_effect=[OSError('403 Blocked'),(rss.encode(),'application/atom+xml','https://www.reddit.com')]) as fetch:
            content,warnings=articles.reddit_comments('https://old.reddit.com/r/test/comments/abc123/title/')
        self.assertEqual(warnings,[])
        self.assertIn('Comments (2 saved)',content)
        self.assertIn('u/Alice',content);self.assertIn('A reply',content)
        self.assertIn('reply nesting and scores are not supplied',content)
        self.assertNotIn('Post text',content);self.assertNotIn('Duplicate',content);self.assertNotIn('Wrong thread',content)
        self.assertEqual(fetch.call_args.args[0],'https://www.reddit.com/comments/abc123/.rss?limit=200&sort=top')
        code='''import sys
sys.path.insert(0,sys.argv[1])
import newsboat_articles as a
page,title,warnings=a.render('<p>Post body.</p>','https://www.reddit.com/r/test/comments/abc123/title/','Test Reddit post',reddit=True,comments=sys.stdin.read())
assert 'Comments (2 saved)' in page and 'u/Alice' in page and 'A reply &amp; more text.' in page
assert '<section id="article-comments">' in page
assert page.count('<script') == 1
'''
        subprocess.run([str(PYTHON),'-c',code,str(SCRIPTS)],input=content,text=True,check=True)

    def test_reddit_rss_rejects_unrelated_or_block_pages(self):
        for response in (b'<html><body>Blocked</body></html>',b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>t3_other</id></entry></feed>'):
            with patch.object(articles,'fetch',side_effect=[ValueError('Not JSON'),(response,'text/html','https://www.reddit.com')]):
                content,warnings=articles.reddit_comments('https://www.reddit.com/r/test/comments/abc123/title/')
            self.assertEqual(warnings,['Reddit comments unavailable'])
            self.assertIn('could not be downloaded',content)
