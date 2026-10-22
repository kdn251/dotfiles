#!/usr/bin/env python3
"""Display actual lifecycle snapshots; a stale monitor never animates as working."""
import html,json,pathlib,time
PATH=pathlib.Path.home()/'.local/state/agent-attention/activity.json'

def render(data,now):
    if not isinstance(data,dict) or now-data.get('updated',0)>8:
        return {'text':'?','class':['unknown','working','f0'],'tooltip':'Agent monitor unavailable; activity is unknown.'}
    state=data.get('state','unknown')
    if state=='idle':return {'text':'','class':['idle'],'tooltip':'No agents currently working'}
    working=data.get('working',0);waiting=data.get('waiting',0)
    text=str(working)+(' !' if waiting else '') if state=='working' else '!' if state=='attention' else '?'
    classes=[state,'f'+str(int(now*12)%24 if state in ('working','attention') else 0)]
    if state=='unknown':classes.append('working')
    lines=['<b>Agent activity</b>',f'{working} working · {waiting} need attention']
    for a in data.get('agents',[]):
        if a['state']=='idle':continue
        age='' if not a.get('activity') else f" · last activity {max(0,int(now-a['activity']))}s ago"
        lines.append(html.escape(f"{a['host']} · {a['agent']} · {a['state']}{age}"))
    if data.get('unavailable'):lines.append('Unavailable monitors: '+html.escape(', '.join(data['unavailable'])))
    lines.append('Working reflects an active turn, not a guarantee of progress.')
    return {'text':text,'class':classes,'tooltip':'\n'.join(lines)}

def main():
    try:
        while True:
            try:data=json.loads(PATH.read_text())
            except (OSError,ValueError):data=None
            print(json.dumps(render(data,time.time())),flush=True)
            time.sleep(1/12)
    except (BrokenPipeError,KeyboardInterrupt):pass

if __name__=='__main__':main()
