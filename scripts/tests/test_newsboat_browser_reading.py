"""Native article progress, registration boundaries, and reader isolation."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
import newsboat_browser_reading as bridge
import newsboat_reading as reading


class BrowserReadingTests(unittest.TestCase):
    def test_old_http_registration_survives_https_and_www_redirect(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reading,'STATE',Path(directory)):
            original='http://www.paulgraham.com/think.html'
            final='https://paulgraham.com/think.html'
            ident=bridge.key(original)
            with closing(bridge.database()) as db, db:
                db.execute('INSERT INTO articles(id,url) VALUES (?,?)',(ident,original))
                db.execute('INSERT INTO browser_articles(url,id) VALUES (?,?)',(original,ident))
            bridge.register(original)
            state=bridge.handle(dict(action='save',url=final,position=dict(fraction=.42,y=1800,anchor=-1,offset=0,text='')))
            self.assertTrue(state['tracked'])
            bridge.register(original)
            restored=bridge.handle(dict(action='get',url=final))
            self.assertEqual(restored['position']['y'],1800)
            self.assertEqual(restored['fraction'],.42)
            self.assertIn(original+'\t42%',(reading.STATE/'download-status.tsv.read').read_text())
            self.assertFalse(bridge.handle(dict(action='get',url=final+'?different=1'))['tracked'])
            self.assertFalse(bridge.handle(dict(action='get',url=final.replace('paulgraham.com','example.org')))['tracked'])
            with closing(bridge.database()) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_articles').fetchone()[0],1)

    def test_original_progress_is_shared_but_positions_are_separate(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reading, 'STATE', Path(directory)):
            url='https://example.org/article'
            self.assertFalse(bridge.handle({'action':'get','url':url})['tracked'])
            bridge.register(url)
            ident=bridge.key(url)
            reading.record(ident,dict(fraction=.3,y=200,anchor=2,offset=4))
            state=bridge.handle(dict(action='save',url=url,position=dict(fraction=.7,y=1900,anchor=10,offset=3,text='Anchor text')))
            self.assertEqual(state['fraction'],.7)
            self.assertEqual(state['position']['y'],1900)
            self.assertEqual(json.loads(reading.lookup(ident)[2])['y'],200)
            self.assertIn(url+'\t70%',(reading.STATE/'download-status.tsv.read').read_text())
            bridge.register(url)  # Reopening does not reset progress.
            self.assertEqual(bridge.handle(dict(action='get',url=url))['position']['y'],1900)
            bridge.handle(dict(action='save',url=url,position=dict(fraction=.2,y=40,anchor=0,offset=0)))
            self.assertEqual(bridge.handle(dict(action='get',url=url))['fraction'],.7)

    def test_reddit_aliases_and_unknown_pages(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reading, 'STATE', Path(directory)):
            url='https://www.reddit.com/r/test/comments/abc/title/'
            bridge.register(url)
            self.assertTrue(bridge.handle(dict(action='get',url=url.replace('www.','old.')+'#comment'))['tracked'])
            self.assertFalse(bridge.handle(dict(action='save',url='https://example.org/private',position={}))['tracked'])
            with closing(reading.database()) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM articles').fetchone()[0],1)
            with self.assertRaises(ValueError):
                bridge.handle(dict(action='save',url=url,position=dict(fraction=float('nan'),y=0,anchor=0,offset=0)))

    def test_real_native_host_framing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reading,'STATE',Path(directory)/'newsboat'):
            url='https://example.org/native';bridge.register(url)
            messages=[dict(action='get',url=url),dict(action='save',url=url,position=dict(fraction=.6,y=400,anchor=1,offset=8)),dict(action='get',url=url)]
            payload=b''
            for message in messages:
                raw=json.dumps(message).encode();payload+=struct.pack('=I',len(raw))+raw
            result=subprocess.run([str(SCRIPTS/'newsboat-browser-reading-host')],input=payload,capture_output=True,check=True,env=dict(os.environ,XDG_STATE_HOME=directory))
            output=result.stdout;responses=[]
            while output:
                length,=struct.unpack('=I',output[:4]);responses.append(json.loads(output[4:4+length]));output=output[4+length:]
            self.assertEqual(len(responses),3)
            self.assertEqual(responses[-1]['position']['y'],400)
            self.assertEqual(responses[-1]['fraction'],.6)

    @unittest.skipUnless(Path('/opt/brave-bin/brave').exists(), 'Brave not installed')
    def test_browser_scroll_without_visible_key_event_saves_and_resumes(self):
        # Vimium consumes j/k. Reproduce its observable result: a scroll without
        # wheel/keydown reaching our script, including the delayed restore retry.
        import base64
        import hashlib
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        import time
        extension=SCRIPTS.parents[1]/'newsboat/browser-extension'
        manifest=json.loads((extension/'manifest.json').read_text())
        digest=hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
        ident=''.join(chr(97+int(c,16)) for c in digest)
        observations=[]
        phase=1
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                if self.path.startswith('/result?'):
                    observations.append((phase,self.path))
                    body=b'ok'
                elif self.path=='/article':
                    body=('<html><body><article>'+''.join(f'<p style="height:100px">Paragraph {i}</p>' for i in range(100))+'</article><script>'+('setTimeout(()=>scrollTo(0,2500),2000);' if phase==1 else '')+'setTimeout(()=>fetch("/result?y="+scrollY),4500);</script></body></html>').encode()
                else:
                    self.send_response(404);self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body)
        with tempfile.TemporaryDirectory() as directory, patch.object(reading,'STATE',Path(directory)/'state/newsboat'):
            root=Path(directory);profile=root/'profile';hosts=profile/'NativeMessagingHosts';hosts.mkdir(parents=True)
            (hosts/'local.newsboat.reading.json').write_text(json.dumps(dict(name='local.newsboat.reading',description='Test bridge',path=str(SCRIPTS/'newsboat-browser-reading-host'),type='stdio',allowed_origins=[f'chrome-extension://{ident}/'])))
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://localhost:{server.server_port}/article'
            # Feed spelling differs from the URL Brave ultimately displays.
            bridge.register(url.replace('://localhost', '://www.localhost'))
            args=['/opt/brave-bin/brave','--headless','--no-first-run','--disable-gpu','--no-default-browser-check','--disable-background-networking','--user-data-dir='+str(profile),'--load-extension='+str(extension),'--app='+url]
            try:
                for step in (1,2):
                    phase=step
                    with (root/f'brave-{step}.log').open('w') as log:
                        process=subprocess.Popen(args,env=dict(os.environ,XDG_STATE_HOME=str(root/'state')),stdout=log,stderr=log)
                        try:
                            deadline=time.monotonic()+12
                            while time.monotonic()<deadline and not any(p==step for p,_ in observations):time.sleep(.1)
                            self.assertIn((step,'/result?y=2500'),observations)
                            state=bridge.handle(dict(action='get',url=url))
                            self.assertGreater(state['fraction'],0)
                            self.assertEqual(state['position']['y'],2500)
                        finally:
                            process.terminate();process.wait(timeout=10)
            finally:
                server.shutdown();server.server_close();thread.join()
