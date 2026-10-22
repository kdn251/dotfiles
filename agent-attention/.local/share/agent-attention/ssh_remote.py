"""Remote standalone SSH event sender and stream; uses only the Python stdlib."""
import json, os, pathlib, sys, time, uuid
ROOT=pathlib.Path.home()/'.local/state/agent-attention-ssh/events'

def build_event(source,payload,environ):
    # Herdr is already monitored separately; detached multiplexers need their own routing.
    if environ.get('HERDR_ENV')=='1' or environ.get('HERDR_PANE_ID') or environ.get('TMUX') or environ.get('STY'):return None
    connection=environ.get('SSH_CONNECTION','').split()
    if len(connection)!=4 or not environ.get('SSH_TTY'):return None
    if source=='Codex':
        if payload.get('type')!='agent-turn-complete':return None
        reason='finished';session=payload.get('thread-id') or 'unknown'
    else:
        event=payload.get('hook_event_name')
        if event=='Notification' and payload.get('notification_type') not in ('permission_prompt','idle_prompt','elicitation_dialog'):return None
        if event=='PreToolUse' and payload.get('tool_name')!='AskUserQuestion':return None
        reasons={'Stop':'finished','PermissionRequest':'approval requested','Notification':'attention requested','PreToolUse':'answer requested','Elicitation':'answer requested'}
        if event not in reasons:return None
        reason=reasons[event];session=payload.get('session_id') or 'unknown'
    return {'source':source,'session':session,'event':reason,'connection':connection,'name':pathlib.PurePosixPath(payload.get('cwd') or '').name or source,'time':time.time()}

def emit(event):
    if not event:return
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    stamp=time.time()
    for old in ROOT.glob('*.json'):
        try:
            if stamp-old.stat().st_mtime>86400:old.unlink()
        except FileNotFoundError:pass
    final=ROOT/(str(uuid.uuid4())+'.json');temporary=final.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(event,f)
    temporary.replace(final)

def watch():
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Start at the live edge: no old completions on startup or SSH reconnect.
    seen={p.name for p in ROOT.glob('*.json')}
    print(json.dumps({'ready':True}),flush=True)
    while True:
        live=list(ROOT.glob('*.json'))
        for path in sorted(live,key=lambda p:p.name):
            if path.name in seen:continue
            try:
                event=json.loads(path.read_text())
                if time.time()-event['time']<30:print(json.dumps({'event':event}),flush=True)
            except (OSError,ValueError,KeyError):pass
        seen={p.name for p in live}
        print(json.dumps({'heartbeat':True}),flush=True);time.sleep(1)

def main():
    mode=sys.argv[1]
    if mode=='watch':watch();return
    if mode=='probe':
        event=build_event('Claude',{'hook_event_name':'Stop','session_id':'ssh-route-probe','cwd':os.getcwd()},os.environ)
        if not event:raise RuntimeError('Probe requires a direct interactive SSH session outside Herdr/tmux')
        event['probe']=True;emit(event);print('SSH route probe sent');return
    try:
        payload=json.loads(sys.argv[2]) if mode=='codex-notify' else json.load(sys.stdin)
        emit(build_event('Codex' if mode=='codex-notify' else 'Claude',payload,os.environ))
    except Exception as exc:print('agent-attention-ssh: '+str(exc),file=sys.stderr)
    finally:
        if mode=='claude-hook':print('{}')
if __name__=='__main__':main()
