#!/usr/bin/env python3
"""Local attention router. Codex metadata polling + Claude hooks; no approval responses."""
import argparse, html, json, logging, logging.handlers, math, os, pathlib, queue, re, socket, subprocess, sys, threading, time
from PIL import Image, ImageFilter, ImageStat
HOME = pathlib.Path.home()
BASE = HOME / '.local/share/agent-attention'
CONFIG = HOME / '.config/agent-attention/config.json'
STATE = HOME / '.local/state/agent-attention'
RUNTIME = pathlib.Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'agent-attention'
EVENTS = queue.Queue()

def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=5)
    if p.returncode: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return p.stdout.strip()

def hypr(verb): return json.loads(run(['hyprctl', verb, '-j']))
def dispatch(action, arg):
    out = run(['hyprctl', 'dispatch', action, arg])
    if out != 'ok': raise RuntimeError(out)
def config(): return json.loads(CONFIG.read_text())
def save_config(c):
    destination = CONFIG.resolve()
    p = destination.with_suffix('.tmp'); p.write_text(json.dumps(c, indent=2)+'\n'); p.replace(destination)
def notify(title, body):
    icon = ['-i', str(BASE / 'codex.png')] if title.startswith('Codex') else []
    run(['notify-send', '-a', 'Agent Attention', '-u', 'normal', '-t', '8000', *icon, title, html.escape(body)])

def ancestors(pid):
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid); yield pid
        try: pid = int(pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError): break

def process_target(pid, kitty_id=None):
    clients = hypr('clients'); target = {}
    for parent in ancestors(pid):
        if not target.get('tty'):
            try:
                tty = os.readlink(f'/proc/{parent}/fd/1')
                if re.fullmatch(r'/dev/pts/\d+', tty): target['tty'] = tty
            except OSError: pass
        for w in clients:
            if w['pid'] == parent:
                target.update(address=w['address'], pid=parent, kitty_id=kitty_id)
                return target
    return {}

def resolve_target(event, clients):
    if event.get('remote'):
        from herdr_attention import resolve
        return resolve(event['remote'],clients,process_target,config().get('herdr_remotes',[]))
    target = event.get('target') or {}
    # Require both live window address and PID, preventing stale/recycled addresses.
    if any(w['address'] == target.get('address') and w['pid'] == target.get('pid') for w in clients): return target
    name = event.get('name') or ''
    matches = [w for w in clients if name and name in w.get('title','') and 'moonlight' not in w['class'].lower()]
    if len(matches) == 1: return {'address':matches[0]['address'], 'pid':matches[0]['pid']}
    return None

def focus(target):
    if target.get('remote'):
        from herdr_attention import focus_remote
        before = hypr('activewindow').get('address')
        focus_remote(target['remote'],config().get('herdr_remotes',[]))
        if hypr('activewindow').get('address') != before:
            raise RuntimeError('Desktop focus changed while selecting the remote pane')
    if target.get('kitty_id') and target.get('tty'):
        message = {'cmd':'focus-window','version':[0,40,0], 'no_response':True,
                   'payload':{'match':f"id:{target['kitty_id']}"}}
        with open(target['tty'], 'wb', buffering=0) as f:
            f.write(b'\x1bP@kitty-cmd'+json.dumps(message).encode()+b'\x1b\\')
    dispatch('focuswindow', 'address:'+target['address'])
    if hypr('activewindow').get('address') != target['address']: raise RuntimeError('Window did not gain focus')

def screen():
    path = RUNTIME / 'screen.png'
    active = hypr('activewindow')
    monitor = next(m for m in hypr('monitors') if m['id'] == active['monitor'])
    run(['grim', '-o', monitor['name'], str(path)])
    im = Image.open(path).convert('L')
    scale = monitor['scale']
    x, y = active['at']; w, h = active['size']
    x -= monitor['x']; y -= monitor['y']
    return im.crop((round(x*scale),round(y*scale),round((x+w)*scale),round((y+h)*scale))).resize((720,480))

def vector(im):
    blurred = im.filter(ImageFilter.GaussianBlur(1))
    return [a-b for a,b in zip(im.getdata(), blurred.getdata())]

def pause_score(im):
    a = vector(im.crop((342,231,378,247)))
    b = vector(Image.open(BASE / 'expedition33-pause.png').convert('L'))
    denom = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/denom if denom else 0

def menu_score(im):
    a = vector(im.crop((99,64,141,82)))
    b = vector(Image.open(BASE / 'expedition33-resume.png').convert('L'))
    denom = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/denom if denom else 0

def detector_score(detector, im):
    return {'expedition33-pause': pause_score, 'expedition33-menu': menu_score}[detector](im)

def cinematic(im):
    # A 16:9 stream on this 3:2 display has 8% bars. Cinematics have ~18%.
    # Sample inside that extra letterbox, not the stream's normal outer bars.
    return max(ImageStat.Stat(im.crop(box)).mean[0] for box in [(50,45,670,68),(50,412,670,435)]) < 8

def select_action(profile, im):
    mode = profile.get('mode','default')
    if mode == 'auto-expedition33':
        if menu_score(im) > .60: mode = 'gameplay'
        else: mode = 'cutscene' if cinematic(im) or pause_score(im) > .60 else 'gameplay'
    return mode, profile['modes'][mode]

def pause_game(profile, active):
    im = screen(); mode, action = select_action(profile, im)
    detector = action.get('detector')
    if detector and detector_score(detector, im) > .60:
        return True, mode+' already paused'
    if not action.get('enabled', False): return False, f'{mode} pause key has not been verified'
    # Recheck immediately before input, and always target the specific stream window.
    if hypr('activewindow').get('address') != active['address']: return False, 'Focus changed before pause'
    key = action['key']; mods = action.get('modifiers','')
    if not re.fullmatch(r'[A-Za-z0-9_]+',key) or not re.fullmatch(r'[A-Z ]*',mods): raise ValueError('Invalid key/modifiers')
    if action.get('hold_ms'):
        if mods: raise ValueError('Held-key profiles currently require no modifiers')
        run(['wtype', '-P', key, '-s', str(int(action['hold_ms'])), '-p', key])
    else:
        dispatch('sendshortcut', f"{mods},{key},address:{active['address']}")
    time.sleep(action.get('settle_ms',700)/1000)
    if detector:
        if hypr('activewindow').get('address') != active['address']: return False, 'Focus changed during pause'
        score = detector_score(detector, screen()); logging.info('Pause visual score %.3f',score)
        return score > .60, f'{mode}: {key}; visual score {score:.3f}'
    return True, f'{mode}: sent {key} (no visual confirmation configured)'

class Router:
    def __init__(self): self.seen = {}; self.last_interrupt = 0
    def handle(self, e):
        c = config()
        if not c.get('enabled'): return
        now = time.monotonic(); identity = (e.get('source'),e.get('session'),e.get('event'))
        if now-self.seen.get(identity,-1000) < c.get('dedupe_seconds',15): return
        self.seen[identity] = now
        if len(self.seen)>1000: self.seen = {k:v for k,v in self.seen.items() if now-v<300}
        active = hypr('activewindow'); target = resolve_target(e,hypr('clients'))
        title = f"{e['source']} needs attention"
        body = f"{e.get('name') or e.get('session','')}: {e.get('event','finished')}"
        logging.info('Attention %s %s %s', e['source'],e.get('session'),e.get('event'))
        if 'moonlight' not in active.get('class','').lower():
            if not target or target['address'] != active.get('address'): notify(title,body)
            return
        if active.get('title') == 'Moonlight' or not target:
            notify(title,body+' — automatic switching unavailable for this session'); return
        if now-self.last_interrupt < c.get('cooldown_seconds',15):
            notify(title,body+' — another alert just interrupted the game'); return
        profile = c.get('games',{}).get(c.get('active_game'))
        if not profile:
            notify(title,body+' — select a game profile to enable pausing'); return
        self.last_interrupt = now
        ok, detail = pause_game(profile,active)
        logging.info('Pause result %s: %s',ok,detail)
        if not ok:
            notify(title,body+' — '+detail+'; staying in Moonlight'); return
        # User may have switched while we were checking; never steal focus then.
        if hypr('activewindow').get('address') == active['address']:
            try:
                focus(target); logging.info('Focused %s%s',target['address'],(' remote '+target['remote']['pane']) if target.get('remote') else '')
            except Exception as exc:
                logging.warning('Focus failed: %s',exc)
                notify(title,body+' — game paused; could not select the agent window');return
        notify(title,body)

def reason(previous, current):
    flags = current.get('activeFlags',[])
    old = (previous or {}).get('activeFlags',[])
    for flag, label in [('waitingOnApproval','approval requested'),('waitingOnUserInput','answer requested')]:
        if flag in flags and flag not in old: return label
    if previous and previous.get('type') == 'active' and current.get('type') == 'idle': return 'finished'
    if previous and previous.get('type') != 'systemError' and current.get('type') == 'systemError': return 'session error'

def codex_watch():
    import websocket
    while True:
        ws = None
        try:
            raw = socket.socket(socket.AF_UNIX); raw.settimeout(5)
            raw.connect(str(HOME / '.codex/app-server-control/app-server-control.sock'))
            ws = websocket.create_connection('ws://localhost',socket=raw,timeout=5,suppress_origin=True)
            seq=0
            def request(method,params):
                nonlocal seq
                seq+=1; ws.send(json.dumps({'id':seq,'method':method,'params':params}))
                while True:
                    result=json.loads(ws.recv())
                    if result.get('id')==seq:
                        if 'error' in result: raise RuntimeError(str(result['error']))
                        return result['result']
                    # Read-only observer: never answer approvals or user questions.
            request('initialize',{'clientInfo':{'name':'agent_attention','version':'1.0'}})
            ws.send('{"method":"initialized"}')
            previous={}; logging.info('Codex observer connected')
            while True:
                ids=[]; cursor=None
                while True:
                    page=request('thread/loaded/list',{'cursor':cursor,'limit':100})
                    ids.extend(page['data']);cursor=page.get('nextCursor')
                    if not cursor:break
                for sid in ids:
                    thread=request('thread/read',{'threadId':sid,'includeTurns':False})['thread']
                    if isinstance(thread.get('source'),dict): continue # background subagents
                    status=thread.get('status',{}); event=reason(previous.get(sid),status)
                    previous[sid]=status
                    if event: EVENTS.put({'source':'Codex','session':sid,'name':thread.get('name'),'event':event})
                previous={k:v for k,v in previous.items() if k in ids}
                time.sleep(2)
        except Exception as exc: logging.warning('Codex observer reconnecting: %s',exc); time.sleep(5)
        finally:
            if ws:
                try:ws.close()
                except Exception:pass

def receive():
    path=RUNTIME/'events.sock'
    path.unlink(missing_ok=True)
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);sock.bind(str(path));os.chmod(path,0o600)
    while True:
        try:
            e=json.loads(sock.recv(32768))
            if e.get('source') in ('Claude','Codex','Test'): EVENTS.put(e)
        except Exception: logging.exception('Invalid attention event')

def send(e):
    s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
    try:s.sendto(json.dumps(e).encode(),str(RUNTIME/'events.sock'))
    finally:s.close()

def claude_hook():
    try:
        p=json.load(sys.stdin);event=p.get('hook_event_name')
        if event=='Notification' and p.get('notification_type') not in ('permission_prompt','idle_prompt','elicitation_dialog'): return
        if event not in ('Stop','PermissionRequest','Notification','PreToolUse','Elicitation'):return
        if event=='PreToolUse' and p.get('tool_name')!='AskUserQuestion':return
        label={'Stop':'finished','PermissionRequest':'approval requested','PreToolUse':'answer requested','Elicitation':'answer requested'}.get(event,'attention requested')
        target=process_target(os.getpid(),os.environ.get('KITTY_WINDOW_ID'))
        send({'source':'Claude','session':p.get('session_id','unknown'),'name':pathlib.Path(p.get('cwd','')).name,'event':label,'target':target})
    except Exception as exc:
        print('agent-attention: '+str(exc),file=sys.stderr)
    finally: print('{}') # Never decide or block approvals/continuation.

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['daemon','claude-hook','status','enable','disable','game','mode','test']);parser.add_argument('value',nargs='?')
    a=parser.parse_args();RUNTIME.mkdir(mode=0o700,parents=True,exist_ok=True);STATE.mkdir(parents=True,exist_ok=True)
    if a.command=='claude-hook':claude_hook();return
    if a.command=='daemon':
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.StreamHandler(),logging.handlers.RotatingFileHandler(STATE/'events.log', maxBytes=1000000, backupCount=2)])
        threading.Thread(target=receive,daemon=True).start();threading.Thread(target=codex_watch,daemon=True).start()
        from herdr_attention import watch
        for endpoint in config().get('herdr_remotes',[]):
            if endpoint.get('enabled',True):threading.Thread(target=watch,args=(endpoint,EVENTS),daemon=True).start()
        router=Router()
        while True:
            e=EVENTS.get()
            try:router.handle(e)
            except Exception:logging.exception('Attention handling failed')
    elif a.command=='test':
        sid=os.environ.get('CODEX_THREAD_ID','manual-test')
        send({'source':'Test','session':sid,'name':'Pause and focus test','event':'test requested','target':process_target(os.getpid(),os.environ.get('KITTY_WINDOW_ID'))})
    else:
        c=config()
        if a.command in ('enable','disable'):c['enabled']=a.command=='enable';save_config(c)
        elif a.command=='game':
            if a.value not in c['games']:parser.error('Choose: '+', '.join(c['games']))
            c['active_game']=a.value;save_config(c)
        elif a.command=='mode':
            p=c['games'][c['active_game']]
            if a.value not in p['modes'] and a.value!='auto-expedition33':parser.error('Unknown mode')
            p['mode']=a.value;save_config(c)
        print(json.dumps(c,indent=2))

if __name__=='__main__':main()
