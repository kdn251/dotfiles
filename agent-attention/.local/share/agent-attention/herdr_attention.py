"""Local SSH observer and exact remote-pane routing for Claude in Herdr."""
import json, logging, os, pathlib, re, select, shlex, subprocess, time
BASE=pathlib.Path(__file__).resolve().parent

def ssh_command(endpoint,mode,expected=None):
    host=endpoint['host']
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*',host):raise ValueError('Invalid SSH alias')
    args=['python3','-u','-c',(BASE/'herdr_remote.py').read_text(),endpoint.get('remote_socket','~/.config/herdr/herdr.sock'),mode]
    if expected is not None:args.append(json.dumps(expected))
    return ['ssh','-T','-S','none','-o','BatchMode=yes','-o','ClearAllForwardings=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',host,shlex.join(args)]

class Tracker:
    def __init__(self):self.previous={};self.pending={}
    def update(self,agents):
        current={};pending={};events=[]
        for a in agents:
            key=(a['pane_id'],a.get('terminal_id'),(a.get('agent_session') or {}).get('value'))
            if not key[1] or not key[2]:continue
            state=a.get('agent_status');seq=a.get('completion_seq') or 0
            old=self.previous.get(key);current[key]=(state,seq)
            reason=None
            if old:
                if state=='blocked' and old[0]!='blocked':reason='approval or answer requested'
                elif state in ('idle','done') and seq>old[1]:reason='finished'
            prior=self.pending.get(key)
            if prior and prior[1]==seq and ((state=='blocked' and prior[0]!='finished') or (state in ('idle','done') and prior[0]=='finished')):
                events.append((a,prior[0]))
            elif reason:pending[key]=(reason,seq)
        self.previous=current;self.pending=pending
        return events

def watch(endpoint,inbox):
    host=endpoint['host']
    while True:
        proc=None
        try:
            proc=subprocess.Popen(ssh_command(endpoint,'watch'),stdout=subprocess.PIPE)
            tracker=Tracker();buf=b'';last=time.monotonic();first=True
            while True:
                if time.monotonic()-last>20:raise RuntimeError('Herdr heartbeat timed out')
                if not select.select([proc.stdout],[],[],1)[0]:continue
                data=os.read(proc.stdout.fileno(),65536)
                if not data:raise RuntimeError('SSH observer disconnected')
                buf+=data
                if len(buf)>4*1024*1024:raise RuntimeError('Oversized Herdr response')
                while b'\n' in buf:
                    line,buf=buf.split(b'\n',1);snapshot=json.loads(line);last=time.monotonic()
                    if first:logging.info('Herdr observer connected: %s (%d Claude panes)',host,len(snapshot['agents']));first=False
                    for agent,reason in tracker.update(snapshot['agents']):
                        identity={'host':host,'pane':agent['pane_id'],'terminal':agent['terminal_id'],'session':agent['agent_session']['value']}
                        name=agent.get('terminal_title_stripped') or pathlib.PurePosixPath(agent.get('cwd') or '').name or 'Claude'
                        inbox.put({'source':'Claude','session':host+':'+identity['session'],'name':host+' · '+name,'event':reason,'remote':identity})
        except Exception as exc:logging.warning('Herdr observer reconnecting (%s): %s',host,exc)
        finally:
            if proc:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
        time.sleep(5)

def resolve(remote,clients,process_target,endpoints):
    if not any(e.get('enabled',True) and e['host']==remote.get('host') for e in endpoints):return None
    matches={}
    for entry in pathlib.Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            args=(entry/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
            if pathlib.Path(args[0]).name!='herdr' or '--remote' not in args:continue
            if args[args.index('--remote')+1]!=remote['host']:continue
            env=dict(x.split('=',1) for x in (entry/'environ').read_bytes().decode().split('\0') if '=' in x)
            target=process_target(int(entry.name),env.get('KITTY_WINDOW_ID'))
            if target:matches[(target['address'],target.get('kitty_id'))]=target
        except (OSError,ValueError,IndexError,UnicodeError):continue
    if len(matches)!=1:return None
    target=next(iter(matches.values()));target['remote']=remote;return target

def focus_remote(remote,endpoints):
    endpoint=next(e for e in endpoints if e.get('enabled',True) and e['host']==remote['host'])
    result=subprocess.run(ssh_command(endpoint,'focus',remote),capture_output=True,text=True,timeout=10)
    if result.returncode or not json.loads(result.stdout).get('focused'):
        raise RuntimeError('Could not select the matching remote Herdr pane: '+result.stderr[-300:])
