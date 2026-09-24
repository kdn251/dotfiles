import sys,subprocess,tempfile,time,json,urllib.request
from pathlib import Path
import threading
import shutil
import unittest
try:
 import websocket
except ImportError:
 websocket=None
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from newsboat_articles import keyboard_support,path_for
import newsboat_reading as reading
import newsboat_media as media

@unittest.skipUnless(websocket and shutil.which('chromium'),'requires Chromium and websocket-client')
class BrowserReadingTests(unittest.TestCase):
 def test_progress_resume_close_and_comment_boundary(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);profile=root/'profile'
   reading.STATE=root/'state';media.ROOT=root/'library'
   article_url='https://example.com/offline'
   page=path_for(article_url);page.parent.mkdir(parents=True)
   page.write_text(keyboard_support('<html><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\';"></head><body><main><header>Article</header><article id="article-content">'+('<p>Long article paragraph</p>'*100)+'</article><section id="article-comments">'+('<p>A comment</p>'*200)+'</section></main></body></html>'))
   ident=reading.register(article_url)
   server=reading.ThreadingHTTPServer(('127.0.0.1',0),reading.Handler)
   server.token='browser-test';server.host=f'127.0.0.1:{server.server_port}'
   threading.Thread(target=server.serve_forever,daemon=True).start()
   reader='http://'+server.host+'/'+server.token+'/article/'+ident
   p=subprocess.Popen(['chromium','--headless','--disable-gpu','--no-first-run','--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+str(profile)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    for _ in range(100):
     if (profile/'DevToolsActivePort').exists():break
     time.sleep(.1)
    port=(profile/'DevToolsActivePort').read_text().splitlines()[0]
    info=json.load(urllib.request.urlopen('http://localhost:'+port+'/json/version'))
    browser=websocket.create_connection(info['webSocketDebuggerUrl']);seq=0
    def call(ws,method,params={}):
     nonlocal seq
     seq+=1;i=seq;ws.send(json.dumps(dict(id=i,method=method,params=params)))
     while True:
      m=json.loads(ws.recv())
      if m.get('id')==i:
       if 'error' in m:raise RuntimeError(m)
       return m.get('result',{})
    target=call(browser,'Target.createTarget',{'url':reader})['targetId']
    targets=json.load(urllib.request.urlopen('http://localhost:'+port+'/json/list'))
    ws=websocket.create_connection(next(x['webSocketDebuggerUrl'] for x in targets if x['id']==target));time.sleep(.5)
    def value(expr):return call(ws,'Runtime.evaluate',{'expression':expr,'returnByValue':True})['result'].get('value')
    def key(k,code=None,modifiers=0):
     call(ws,'Input.dispatchKeyEvent',{'type':'keyDown','key':k,'code':code or 'Key'+k.upper(),'modifiers':modifiers})
     call(ws,'Input.dispatchKeyEvent',{'type':'keyUp','key':k,'code':code or 'Key'+k.upper(),'modifiers':modifiers})
    assert value('typeof window.newsboatSaveReading')=='function'
    def progress():
     return json.load(urllib.request.urlopen(reader.replace('/article/','/progress/')))
    assert progress()['fraction']==0
    value('scrollTo(0,1800)');time.sleep(.5)
    high=progress()['fraction'];assert 0<high<1,high
    value('scrollTo(0,800)');time.sleep(.5)
    saved=progress();assert saved['fraction']==high
    assert saved['position']['y']==800
    call(ws,'Input.dispatchKeyEvent',{'type':'keyDown','key':'q','code':'KeyQ'});time.sleep(.3)
    assert target not in [x['targetId'] for x in call(browser,'Target.getTargets')['targetInfos']]
    target=call(browser,'Target.createTarget',{'url':reader})['targetId']
    targets=json.load(urllib.request.urlopen('http://localhost:'+port+'/json/list'))
    ws=websocket.create_connection(next(x['webSocketDebuggerUrl'] for x in targets if x['id']==target));time.sleep(.6)
    assert abs(value('scrollY')-800)<3,value('scrollY')
    assert progress()['fraction']==high
    value("scrollTo(0,document.getElementById('article-comments').offsetTop)");time.sleep(.5)
    assert progress()['fraction']==1,progress()
    value('scrollTo(0,document.documentElement.scrollHeight)');time.sleep(.5)
    assert progress()['fraction']==1
    print('Browser passed: progress, highest percentage, q save/close, paragraph resume, comments excluded')
   finally:
    p.terminate();p.wait(timeout=10)
    server.shutdown();server.server_close()
