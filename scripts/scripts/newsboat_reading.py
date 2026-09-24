"""Loopback-only article reader and persistent reading position service."""
from contextlib import closing
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

from newsboat_articles import canonical, key, find, keyboard_support
from newsboat_media import atomic_write

STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
LOCK = threading.Lock()


def database():
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE/'reading-progress.db'
    db = sqlite3.connect(path, timeout=5)
    path.chmod(0o600)
    db.execute('CREATE TABLE IF NOT EXISTS articles (id TEXT PRIMARY KEY, url TEXT, fraction REAL DEFAULT 0, position TEXT DEFAULT \'{}\', updated REAL DEFAULT 0)')
    return db


def register(url):
    url = canonical(url)
    if not find(url):
        raise ValueError('No downloaded article exists')
    ident = key(url)
    with closing(database()) as db, db:
        db.execute('INSERT OR IGNORE INTO articles(id,url) VALUES (?,?)', (ident,url))
    return ident


def lookup(ident):
    with closing(database()) as db:
        row = db.execute('SELECT url,fraction,position FROM articles WHERE id=?', (ident,)).fetchone()
    return row


def record(ident, data):
    fraction = data.get('fraction')
    y, anchor, offset = data.get('y'), data.get('anchor'), data.get('offset')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (fraction,y,offset)) or not isinstance(anchor,int):
        raise ValueError('Invalid reading position')
    if not 0 <= fraction <= 1 or not 0 <= y <= 1e8 or not -1 <= anchor <= 100000 or abs(offset)>1e8:
        raise ValueError('Invalid reading position')
    position = json.dumps(dict(y=y,anchor=anchor,offset=offset))
    with LOCK, closing(database()) as db, db:
        if not db.execute('SELECT 1 FROM articles WHERE id=?',(ident,)).fetchone():
            raise ValueError('Unknown article')
        db.execute('UPDATE articles SET fraction=MAX(fraction,?), position=?, updated=? WHERE id=?',
                   (fraction,position,time.time(),ident))
        db.commit()
        rows=db.execute('SELECT url,fraction FROM articles').fetchall()
        atomic_write(STATE/'download-status.tsv.read', ''.join(f'{url}\t{min(100,int(value*100))}%\n' for url,value in rows))


READING_JS = r'''(() => {
  if (!/^http:\/\/127\.0\.0\.1:/.test(location.href)) return;
  const endpoint = location.pathname.replace('/article/', '/progress/');
  const content = document.getElementById('article-content') || document.querySelector('main > section');
  if (!content) return;
  const blocks = [...document.querySelectorAll('#article-content p, #article-content h1, #article-content h2, #article-content h3, #article-content li, #article-content pre, #article-comments p, main > section p, main > section h2')];
  // Older saved pages placed comments inside the body. Exclude those too.
  const comments = document.getElementById('article-comments') || [...content.querySelectorAll('h2')].find(h => /^Comments(?:\s|$)/.test(h.textContent));
  let ready = false, engaged = false, furthest = 0, timer = 0;
  const top = element => element.getBoundingClientRect().top + scrollY;
  function snapshot() {
    const start = top(content);
    const end = comments ? top(comments) : top(content) + content.getBoundingClientRect().height;
    // Use the viewport's reading edge; merely opening a page leaves it at 0%.
    let fraction = engaged ? Math.max(0, Math.min(1, (scrollY + innerHeight * .8 - start) / Math.max(1,end-start))) : 0;
    if (engaged && (scrollY + innerHeight >= end - 8)) fraction = 1;
    furthest = Math.max(furthest, fraction);
    let anchor = -1;
    for (let i=0;i<blocks.length;i++) {
      if (top(blocks[i]) <= scrollY + 16) anchor = i; else break;
    }
    return {fraction:furthest,y:scrollY,anchor,offset:anchor<0?0:scrollY-top(blocks[anchor])};
  }
  function save() {
    clearTimeout(timer);
    if (!ready) return Promise.resolve();
    return fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(snapshot()),keepalive:true}).catch(()=>{});
  }
  window.newsboatSaveReading = save;
  const engage = () => { if (ready) engaged = true; };
  window.addEventListener('wheel', engage, {passive:true});
  window.addEventListener('touchmove', engage, {passive:true});
  window.addEventListener('keydown', e => {
    if (['j','k','g','G',' ','PageDown','PageUp','ArrowDown','ArrowUp','End','Home','d','u'].includes(e.key)) engage();
  });
  window.addEventListener('scroll', () => {
    if (!ready) return;
    engaged = true;
    clearTimeout(timer); timer=setTimeout(save,200);
  },{passive:true});
  const periodic = setInterval(() => {if (ready && engaged) save();},1000);
  window.addEventListener('pagehide', () => {save(); clearInterval(periodic);});
  document.addEventListener('visibilitychange', () => {if(document.hidden) save();});
  async function restore() {
    try {
      const response = await fetch(endpoint);
      const state = await response.json();
      furthest = state.fraction || 0;
      const pos = state.position || {};
      const element = blocks[pos.anchor];
      scrollTo(0, element ? top(element)+(pos.offset||0) : (pos.y||0));
    } catch (_) {}
    // Discard the programmatic restore's scroll event.
    requestAnimationFrame(() => requestAnimationFrame(() => {ready=true;}));
  }
  if (document.readyState==='complete') restore(); else window.addEventListener('load',restore,{once:true});
})();'''


def enhance(page):
    import base64
    page = keyboard_support(page)
    digest=base64.b64encode(hashlib.sha256(READING_JS.encode()).digest()).decode()
    # Only our two fixed scripts may execute; no original site scripts/network.
    page=page.replace("script-src 'sha256-", "connect-src 'self'; script-src 'sha256-",1)
    start=page.index('script-src ')
    end=page.index(';',start)
    page=page[:end]+" 'sha256-"+digest+"'"+page[end:]
    return page.replace('</body>','<script>'+READING_JS+'</script></body>')


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass

    def reply(self, status, body, mime='application/json'):
        if isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',mime+'; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        if self.headers.get('Host') != self.server.host:
            return None
        parts=self.path.split('/')
        if len(parts)<3 or not secrets.compare_digest(parts[1],self.server.token): return None
        if parts[2]=='health' and len(parts)==3:return ('health',None)
        if len(parts)!=4 or parts[2] not in {'article','progress'}:return None
        return parts[2],parts[3]

    def do_GET(self):
        route=self.route()
        if not route:return self.reply(404,'{}')
        kind,ident=route
        if kind=='health':return self.reply(200,'{}')
        row=lookup(ident)
        if not row:return self.reply(404,'{}')
        url,fraction,position=row
        if kind=='progress':return self.reply(200,json.dumps(dict(fraction=fraction,position=json.loads(position))))
        path=find(url)
        if not path:return self.reply(404,'Downloaded article was deleted','text/plain')
        return self.reply(200,enhance(path.read_text()),'text/html')

    def do_POST(self):
        route=self.route()
        origin=self.headers.get('Origin')
        if not route or route[0]!='progress' or origin not in {None,'http://'+self.server.host}:
            return self.reply(403,'{}')
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096:raise ValueError('Invalid body')
            record(route[1],json.loads(self.rfile.read(size)))
            return self.reply(200,'{}')
        except (ValueError,TypeError,AttributeError):return self.reply(400,'{}')


def serve():
    os.umask(0o077)
    STATE.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.token=secrets.token_urlsafe(32)
    server.host=f'127.0.0.1:{server.server_port}'
    atomic_write(STATE/'article-server.json',json.dumps(dict(base='http://'+server.host+'/'+server.token,pid=os.getpid())))
    server.serve_forever()


def existing_server():
    try:
        info=json.loads((STATE/'article-server.json').read_text())
        if not info['base'].startswith('http://127.0.0.1:'):return None
        with urlopen(info['base']+'/health',timeout=.3) as response:
            if response.status==200:return info['base']
    except (OSError,ValueError,KeyError):pass
    return None


def reader_url(url):
    ident=register(url)
    with (STATE/'article-server.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        base=existing_server()
        if not base:
            with (STATE/'article-server.log').open('a') as log:
                subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'serve'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            for _ in range(40):
                time.sleep(.05)
                base=existing_server()
                if base:break
        if not base:raise RuntimeError('The local article reader could not start')
    return base+'/article/'+ident


if __name__=='__main__':
    if sys.argv[1:] == ['serve']:serve()
    else:print(reader_url(sys.argv[1]))
