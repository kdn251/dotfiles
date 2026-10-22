"""Combine fresh monitor snapshots for Waybar, independently of interruption events."""
import json,logging,pathlib,threading,time
from activity_probe import Probe
LOCK=threading.Lock()
SOURCES={}
PATH=pathlib.Path.home()/'.local/state/agent-attention/activity.json'

def update(source,host,items):
    with LOCK:SOURCES[source]={'host':host,'items':items,'updated':time.time()}

def summarize(sources,now):
    agents={};unavailable=[]
    for source,data in sources.items():
        if now-data['updated']>8:
            unavailable.append(source);continue
        for row in data['items']:
            key=(data['host'],row['agent'],row['id'])
            # Explicit API status takes precedence over rollout inference.
            if key in agents and source!='local-codex':
                for field,value in row.items():
                    if agents[key].get(field) is None:agents[key][field]=value
                continue
            item={**row,'host':data['host']}
            if key in agents:
                for field,value in agents[key].items():
                    if item.get(field) is None:item[field]=value
            agents[key]=item
    rows=list(agents.values())
    working=sum(a['state']=='working' for a in rows)
    waiting=sum(a['state']=='attention' for a in rows)
    unknown=sum(a['state']=='unknown' for a in rows)
    state='working' if working else 'attention' if waiting else 'unknown' if unknown or unavailable else 'idle'
    return {'updated':now,'state':state,'working':working,'waiting':waiting,'unknown':unknown,'unavailable':unavailable,'agents':rows}

def herdr_snapshot(host,agents):
    items=[]
    for a in agents:
        state={'busy':'working','running':'working','working':'working','active':'working','blocked':'attention','idle':'idle','done':'idle'}.get(a.get('agent_status'),'unknown')
        sid=(a.get('agent_session') or {}).get('value') or a['pane_id']
        route={'host':host,'pane':a['pane_id'],'terminal':a.get('terminal_id'),'session':sid,'agent':a.get('agent')}
        items.append({'id':sid,'agent':str(a.get('agent','Agent')).capitalize(),'name':a.get('terminal_title_stripped') or pathlib.Path(a.get('cwd') or '').name,'state':state,'activity':None,'model':a.get('model'),'completed':a.get('completion_seq'),'remote':route})
    update('herdr:'+host,host,items)

class Completions:
    def __init__(self):self.previous={};self.until=0;self.names=[]
    def apply(self,result,now):
        current={};names=[]
        for a in result['agents']:
            key=(a['host'],a['agent'],a['id']);value=a.get('completed') or 0
            current[key]=value if a['state']=='idle' else self.previous.get(key,value)
            if key in self.previous and value>self.previous[key] and a['state']=='idle':names.append(a.get('name') or a['agent'])
        self.previous=current
        if names:self.until=now+6;self.names=names
        if now<self.until:
            result['completion']={'until':self.until,'names':self.names}
            if result['state']=='idle':result['state']='complete'
        return result

def watch(config):
    probe=Probe()
    completions=Completions()
    for kind,key in [('ssh','ssh_remotes'),('herdr','herdr_remotes')]:
        for e in config.get(key,[]):
            if e.get('enabled',True):
                with LOCK:SOURCES.setdefault(kind+':'+e['host'],{'host':e['host'],'items':[],'updated':0})
    while True:
        try:
            update('local-probe','local',probe.snapshot())
            with LOCK:result=summarize(SOURCES,time.time())
            result=completions.apply(result,time.time())
            PATH.parent.mkdir(parents=True,exist_ok=True)
            tmp=PATH.with_suffix('.tmp');tmp.write_text(json.dumps(result));tmp.chmod(0o600);tmp.replace(PATH)
        except Exception:logging.exception('Activity monitor failed')
        time.sleep(2)
