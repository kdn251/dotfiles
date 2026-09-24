"""Reader persistence and local HTTP access controls."""
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import newsboat_reading as reading
import newsboat_media as media
from newsboat_articles import path_for,keyboard_support


class ReadingTests(unittest.TestCase):
    def test_progress_keeps_maximum_but_restores_latest_position(self):
        with tempfile.TemporaryDirectory() as d, patch.object(reading,'STATE',Path(d)/'state'), patch.object(media,'ROOT',Path(d)/'library'):
            url='https://example.com/article'
            path=path_for(url);path.parent.mkdir(parents=True);path.write_text('article')
            ident=reading.register(url)
            reading.record(ident,dict(fraction=.7,y=900,anchor=12,offset=8))
            reading.record(ident,dict(fraction=.3,y=300,anchor=4,offset=5))
            row=reading.lookup(ident)
            self.assertEqual(row[1],.7)
            self.assertEqual(json.loads(row[2]),dict(y=300,anchor=4,offset=5))
            self.assertIn(url+'\t70%',(reading.STATE/'download-status.tsv.read').read_text())
            with self.assertRaises(ValueError):reading.record(ident,dict(fraction=float('nan'),y=0,anchor=0,offset=0))

    def test_server_serves_only_registered_articles_and_rejects_foreign_posts(self):
        with tempfile.TemporaryDirectory() as d, patch.object(reading,'STATE',Path(d)/'state'), patch.object(media,'ROOT',Path(d)/'library'):
            url='https://example.com/article';path=path_for(url);path.parent.mkdir(parents=True)
            path.write_text(keyboard_support('<html><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\';"></head><body><article id="article-content">Body</article></body></html>'))
            ident=reading.register(url)
            server=reading.ThreadingHTTPServer(('127.0.0.1',0),reading.Handler)
            server.token='test-token';server.host=f'127.0.0.1:{server.server_port}'
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://'+server.host
            try:
                with urlopen(base+'/test-token/article/'+ident) as response:
                    page=response.read().decode()
                self.assertIn('newsboatSaveReading',page)
                self.assertIn("connect-src 'self'",page)
                self.assertEqual(page.count('<script'),2)
                payload=json.dumps(dict(fraction=.2,y=50,anchor=1,offset=0)).encode()
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base+'/test-token/progress/'+ident,data=payload,headers={'Origin':'https://example.com'}))
                self.assertEqual(error.exception.code,403)
                with urlopen(Request(base+'/test-token/progress/'+ident,data=payload,headers={'Origin':base})) as response:
                    self.assertEqual(response.status,200)
                with urlopen(base+'/test-token/progress/'+ident) as response:
                    self.assertEqual(json.load(response)['fraction'],.2)
                with self.assertRaises(HTTPError):urlopen(base+'/wrong/article/'+ident)
            finally:server.shutdown();server.server_close();thread.join()
