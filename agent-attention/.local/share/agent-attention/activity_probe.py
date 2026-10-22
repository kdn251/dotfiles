"""Read local agent lifecycle metadata. No prompts or output are exported."""
import datetime,json,os,pathlib,sys,time
HOME=pathlib.Path.home()
HOOKS=HOME/'.local/state/agent-attention/activity-claude'

def stamp(value):
    try:return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,AttributeError):return time.time()

def process_identity(pid):
    fields=pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    return int(fields[1]),fields[19]

def claude_owner():
    pid=os.getppid()
    while pid>1:
        p=pathlib.Path(f'/proc/{pid}')
        parent,start=process_identity(pid)
        args=(p/'cmdline').read_bytes().replace(b'\0',b' ')
        if (p/'comm').read_text().strip()=='claude' or b'@anthropic-ai/claude-code/' in args:return pid,start
        pid=parent
    return None

def claude_state(payload):
    event=payload.get('hook_event_name')
    if event in ('Stop','SessionEnd'):return 'idle'
    if event in ('PermissionRequest','Elicitation'):return 'attention'
    if event=='Notification':
        return 'attention' if payload.get('notification_type') in ('permission_prompt','elicitation_dialog') else None
    if event=='PreToolUse' and payload.get('tool_name')=='AskUserQuestion':return 'attention'
    if event in ('UserPromptSubmit','PreToolUse','PostToolUse','PostToolUseFailure','ElicitationResult'):return 'working'
    return None

def claude_hook():
    try:
        data=json.load(sys.stdin);state=claude_state(data);owner=claude_owner()
        if not state or not owner:return
        sid=data.get('session_id')
        if not sid or not all(c.isalnum() or c in '-_' for c in sid):return
        HOOKS.mkdir(parents=True,exist_ok=True,mode=0o700)
        item={'id':sid,'agent':'Claude','state':state,'activity':time.time(),'pid':owner[0],'start':owner[1]}
        path=HOOKS/(sid+'.json');tmp=path.with_suffix(f'.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(item));tmp.chmod(0o600);tmp.replace(path)
    except (OSError,ValueError,KeyError):pass
    finally:print('{}')

def install_hooks(data,command):
    hooks=data.setdefault('hooks',{})
    events=('UserPromptSubmit','PreToolUse','PostToolUse','PostToolUseFailure','PermissionRequest','Stop','SessionEnd','Notification','Elicitation','ElicitationResult')
    for event in events:
        groups=[]
        for original in hooks.get(event,[]):
            group=dict(original);group['hooks']=[h for h in group.get('hooks',[]) if 'activity_probe.py' not in h.get('command','')]
            if group['hooks']:groups.append(group)
        groups.append({'hooks':[{'type':'command','command':command,'timeout':5}]})
        hooks[event]=groups

class Probe:
    def __init__(self):self.files={}
    def rollout(self,path):
        stat=path.stat();cache=self.files.get(str(path))
        if not cache or cache['inode']!=stat.st_ino or cache['offset']>stat.st_size:
            cache={'inode':stat.st_ino,'offset':0,'item':None};self.files[str(path)]=cache
        with path.open('rb') as stream:
            stream.seek(cache['offset'])
            while True:
                start=stream.tell();line=stream.readline()
                if not line or not line.endswith(b'\n'):break
                cache['offset']=stream.tell()
                try:record=json.loads(line)
                except ValueError:continue
                data=record.get('payload',{});kind=record.get('type')
                if kind=='session_meta':
                    if isinstance(data.get('source'),dict) or data.get('thread_source','user')!='user':
                        cache['excluded']=True;return None
                    cache['item']={'id':data.get('id'),'agent':'Codex','name':pathlib.Path(data.get('cwd') or '').name,'state':'idle','activity':stamp(record.get('timestamp'))}
                item=cache['item']
                if not item:continue
                if kind=='event_msg':
                    typ=data.get('type')
                    if typ=='task_started':item['state']='working'
                    elif typ in ('task_complete','task_aborted'):item['state']='idle'
                    elif typ in ('request_user_input','exec_approval_request','apply_patch_approval_request'):item['state']='attention'
                if kind in ('event_msg','response_item'):item['activity']=stamp(record.get('timestamp'))
        return None if cache.get('excluded') else cache['item']
    def snapshot(self):
        rollouts=set();claudes={}
        for p in pathlib.Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if p.stat().st_uid!=os.getuid():continue
                name=(p/'comm').read_text().strip()
                if name not in ('codex','claude','node'):continue
                if name=='node' and b'@anthropic-ai/claude-code/' not in (p/'cmdline').read_bytes():continue
                if name in ('claude','node'):
                    env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode().split('\0') if '=' in x)
                    if env.get('HERDR_ENV')=='1' or env.get('HERDR_PANE_ID'):continue
                    claudes[int(p.name)]=process_identity(int(p.name))[1]
                if name=='codex':
                    for fd in (p/'fd').iterdir():
                        try:target=os.readlink(fd)
                        except OSError:continue
                        if '/sessions/' in target and '/rollout-' in target and target.endswith('.jsonl'):rollouts.add(target)
            except (OSError,ValueError,UnicodeError):continue
        items=[]
        for name in rollouts:
            try:
                item=self.rollout(pathlib.Path(name))
                if item:items.append(dict(item))
            except (OSError,ValueError):continue
        self.files={k:v for k,v in self.files.items() if k in rollouts}
        covered=set()
        for path in HOOKS.glob('*.json'):
            try:
                item=json.loads(path.read_text());pid=item['pid']
                if claudes.get(pid)!=item['start']:continue
                row={k:item[k] for k in ('id','agent','state','activity')}
                proc=pathlib.Path('/proc')/str(pid)
                row['name']=pathlib.Path(os.readlink(proc/'cwd')).name
                row['background']=os.readlink(proc/'fd/0')=='/dev/null'
                covered.add(pid);items.append(row)
            except (OSError,ValueError,KeyError):continue
        for pid in claudes.keys()-covered:
            items.append({'id':f'pid:{pid}','agent':'Claude','state':'unknown','activity':None})
        return items

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='claude-hook':claude_hook()
    else:print(json.dumps(Probe().snapshot()))
