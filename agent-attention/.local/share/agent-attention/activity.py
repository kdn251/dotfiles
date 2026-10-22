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
                if agents[key].get('activity') is None:agents[key]['activity']=row.get('activity')
                continue
            item={**row,'host':data['host']}
            if item.get('activity') is None and key in agents:item['activity']=agents[key].get('activity')
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
        items.append({'id':(a.get('agent_session') or {}).get('value') or a['pane_id'],'agent':str(a.get('agent','Agent')).capitalize(),'name':a.get('terminal_title_stripped') or pathlib.Path(a.get('cwd') or '').name,'state':state,'activity':None})
    update('herdr:'+host,host,items)

def watch(config):
    probe=Probe()
    for kind,key in [('ssh','ssh_remotes'),('herdr','herdr_remotes')]:
        for e in config.get(key,[]):
            if e.get('enabled',True):
                with LOCK:SOURCES.setdefault(kind+':'+e['host'],{'host':e['host'],'items':[],'updated':0})
    while True:
        try:
            update('local-probe','local',probe.snapshot())
            with LOCK:result=summarize(SOURCES,time.time())
            PATH.parent.mkdir(parents=True,exist_ok=True)
            tmp=PATH.with_suffix('.tmp');tmp.write_text(json.dumps(result));tmp.chmod(0o600);tmp.replace(PATH)
        except Exception:logging.exception('Activity monitor failed')
        time.sleep(2)
