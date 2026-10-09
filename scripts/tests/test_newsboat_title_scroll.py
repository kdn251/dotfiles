import tempfile
from pathlib import Path
import unittest
from test_newsboat_reconnect import reader

class TitleScrollTests(unittest.TestCase):
    def test_selected_title_scrolls_and_resets_without_moving_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);feed=root/'feed.xml'
            title='BEGIN '+('x'*108)+' END-MARK'
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description>'+''.join(f'<item><title>{title}</title><link>https://example.org/{i}</link><guid>{i}</guid></item>' for i in range(2))+'</channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles yes\narticle-sort-order guid-asc\narticlelist-format "%4i │ %t"\nrun-on-startup open\nbind-key j down\n'
            with reader(root,cfg,feed.as_uri()+'\n') as (_,screen,send,wait):
                wait(lambda s:'BEGIN' in screen.display[1] and 'BEGIN' in screen.display[2])
                prefix=screen.display[1][:7]
                wait(lambda s:'END-MARK' in screen.display[1],timeout=12)
                self.assertEqual(screen.display[1][:7],prefix)
                self.assertIn('BEGIN',screen.display[2])
                send('j');wait(lambda s:screen.cursor.y==2 and 'BEGIN' in screen.display[2])
                self.assertIn('BEGIN',screen.display[1])
                wait(lambda s:'END-MARK' in screen.display[2],timeout=12)
                self.assertIn('BEGIN',screen.display[1])

    def test_cached_long_row_starts_scrolling_during_reload(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        blocked=threading.Event(); release=threading.Event(); refreshing=threading.Event()
        title='BEGIN '+('x'*108)+' END-MARK'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                if refreshing.is_set():
                    blocked.set(); release.wait(12)
                body='<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description>'
                for i,text in enumerate(['Short',title]):
                    body+=f'<item><title>{text}</title><link>https://example.org/{i}</link><guid>{i}</guid></item>'
                self.send_response(200);self.end_headers();self.wfile.write((body+'</channel></rss>').encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                cfg='show-read-feeds yes\nshow-read-articles yes\narticle-sort-order guid-asc\narticlelist-format "%4i │ %t"\nrun-on-startup open\nbind-key j down\nbind-key R reload-all\n'
                with reader(Path(directory),cfg,f'http://127.0.0.1:{server.server_port}/feed\n') as (_,screen,send,wait):
                    wait(lambda s:'Short' in screen.display[1] and 'BEGIN' in screen.display[2])
                    refreshing.set();send('R');wait(lambda s:blocked.is_set())
                    send('j');wait(lambda s:screen.cursor.y==2)
                    wait(lambda s:'END-MARK' in screen.display[2],timeout=7)
                    self.assertFalse(release.is_set())
                    self.assertIn('Short',screen.display[1])
                    release.set()
        finally:
            release.set();server.shutdown();server.server_close();thread.join()
