#!/usr/bin/env python3
"""Display actual lifecycle snapshots; a stale monitor never animates as working."""
import html,json,pathlib,time,sys
PATH=pathlib.Path.home()/'.local/state/agent-attention/activity.json'
PREVIEW=PATH.with_name('completion-preview.json')
CLASSIC='--classic' in sys.argv

def render_status(data,now):
    if not isinstance(data,dict) or now-data.get('updated',0)>8:
        return {'text':'?','class':['unknown','working','f0'],'tooltip':'Agent monitor unavailable; activity is unknown.'}
    state=data.get('state','unknown')
    if state=='idle':return {'text':'·','class':['resting','working','f0'],'tooltip':'All monitored agents are idle. Click to view sessions.'}
    working=data.get('working',0);waiting=data.get('waiting',0)
    text=str(working)+(' !' if waiting else ' ·' if data.get('completion') else '') if state=='working' else '!' if state=='attention' else '·' if state=='complete' else '?'
    classes=[state,'f'+str(int(now*12)%24 if state in ('working','attention','complete') else 0)]
    if data.get('unavailable') or data.get('unknown'):classes.append('uncertain');text+=' ?' if text!='?' else ''
    if state=='unknown':classes.append('working')
    lines=['<b>Agent activity</b>',f'{working} working · {waiting} need attention']
    for a in data.get('agents',[]):
        if a['state']=='idle':continue
        age='' if not a.get('activity') else f" · last activity {max(0,int(now-a['activity']))}s ago"
        name=a.get('name') or a.get('id','')[:8]
        background=' (background)' if a.get('background') else ''
        lines.append(html.escape(f"{a['host']} · {a['agent']} · {name}{background}\n  {a['state']}{age}"))
    if data.get('unavailable'):lines.append('Unavailable monitors: '+html.escape(', '.join(data['unavailable'])))
    if data.get('completion'):lines.append('Finished: '+html.escape(', '.join(data['completion'].get('names',[]))))
    lines.append('Working reflects an active turn, not a guarantee of progress.')
    return {'text':text,'class':classes,'tooltip':'\n'.join(lines)}

def render(data,now):
    result=render_status(data,now)
    if not CLASSIC and 'working' in result['class']:
        # Frozen idle/unknown snapshots must never imply an active agent.
        active=isinstance(data,dict) and data.get('state')=='working' and now-data.get('updated',0)<=8
        frame=int(now*32)%96 if active else 0
        result['class']=[c for c in result['class'] if not (c.startswith('f') and c[1:].isdigit())]+['painted','f'+str(frame)]
    return result

def main():
    if '--preview-complete' in sys.argv:
        PREVIEW.write_text(json.dumps({'until':time.time()+15}));return
    try:
        while True:
            try:data=json.loads(PATH.read_text())
            except (OSError,ValueError):data=None
            result=render(data,time.time())
            try:
                if json.loads(PREVIEW.read_text())['until']>time.time():
                    result={'text':'·','class':['complete','f'+str(int(time.time()*12)%24)],'tooltip':'Completion animation preview (15 seconds). Real monitoring continues.'}
            except (OSError,ValueError,KeyError):pass
            print(json.dumps(result),flush=True)
            time.sleep(1/12 if CLASSIC else 1/32)
    except (BrokenPipeError,KeyboardInterrupt):pass

if __name__=='__main__':main()
