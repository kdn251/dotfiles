#!/usr/bin/env python3
"""Translate this desktop's pre-0.57 IPC commands; pass modern/read-only IPC through."""
import json
import os
import re
import subprocess
import sys
import zlib

REAL = '/usr/bin/hyprctl'
def lua(v):
    if isinstance(v, dict): return '{' + ','.join('['+lua(k)+']='+lua(x) for k,x in v.items()) + '}'
    if isinstance(v, bool): return str(v).lower()
    if isinstance(v, (int,float)): return str(v)
    return json.dumps(v, ensure_ascii=False)
def scalar(v):
    if v in ('true','on'): return True
    if v in ('false','off'): return False
    try: return float(v) if '.' in v else int(v)
    except ValueError: return v

def dispatcher(name, arg):
    opts={}; direction={'l':'left','r':'right','u':'up','d':'down'}
    def call(method, value=None):
        return 'hl.dispatch(hl.dsp.'+method+'('+('' if value is None else lua(value))+'))'
    if name=='exec':
        rules={}
        if arg.startswith('['):
            raw,arg=arg[1:].split(']',1)
            for rule in raw.split(';'):
                key,_,value=rule.strip().partition(' '); rules[key]=scalar(value) if value else True
        return 'hl.exec_cmd('+lua(arg.strip())+(','+lua(rules) if rules else '')+')'
    if name in ('focuswindow','focusmonitor','workspace','movefocus'):
        key={'focuswindow':'window','focusmonitor':'monitor','workspace':'workspace','movefocus':'direction'}[name]
        return call('focus',{key:direction.get(arg,arg) if key=='direction' else arg})
    if name in ('movetoworkspace','movetoworkspacesilent'):
        parts=arg.split(',',1); opts={'workspace':parts[0],'follow':name=='movetoworkspace'}
        if len(parts)>1: opts['window']=parts[1]
        return call('window.move',opts)
    if name in ('movewindowpixel','resizewindowpixel'):
        parts=arg.split(',',1); xy=parts[0].split(); exact=xy[0]=='exact'
        if exact: xy=xy[1:]
        opts={'x':scalar(xy[0]),'y':scalar(xy[1]),'relative':not exact}
        if len(parts)>1: opts['window']=parts[1]
        return call('window.'+('move' if name=='movewindowpixel' else 'resize'),opts)
    if name=='movewindow': return call('window.move',{'direction':direction.get(arg,arg)})
    if name=='moveworkspacetomonitor':
        ws,monitor=arg.split(' ',1); return call('workspace.move',{'workspace':ws,'monitor':monitor})
    if name=='movecursor':
        x,y=arg.split(); return call('cursor.move',{'x':scalar(x),'y':scalar(y)})
    if name in ('closewindow','killactive','pin','setfloating','settiled','togglefloating'):
        if arg: opts['window']=arg
        method={'closewindow':'close','killactive':'close','pin':'pin','setfloating':'float','settiled':'float','togglefloating':'float'}[name]
        if name in ('setfloating','settiled'): opts['action']='on' if name=='setfloating' else 'off'
        return call('window.'+method,opts)
    if name=='setprop':
        win,prop,value=arg.split(' ',2)
        return call('window.set_prop',{'window':win,'prop':prop,'value':value})
    if name=='fullscreen': return call('window.fullscreen',{'mode':'maximized' if arg=='1' else 'fullscreen','action':'toggle'})
    if name=='fullscreenstate':
        internal,client,*action=arg.split(); opts={'internal':int(internal),'client':int(client),'action':{'0':'set','1':'toggle','2':'unset'}.get(action[0],'set') if action else 'set'}
        return call('window.fullscreen_state',opts)
    if name=='togglespecialworkspace': return call('workspace.toggle_special',arg.removeprefix('special:'))
    if name=='changegroupactive': return call('group.'+('prev' if arg=='b' else 'next')) if arg in ('f','b') else call('group.active',{'index':int(arg)})
    if name=='cyclenext': return call('window.cycle_next',{'next':'prev' not in arg,'tiled':'tiled' in arg,'floating':'floating' in arg})
    if name=='layoutmsg': return call('layout',arg)
    if name=='dpms':
        parts=arg.split(); opts={'action':parts[0]}
        if len(parts)>1: opts['monitor']=parts[1]
        return call('dpms',opts)
    if name=='sendshortcut':
        parts=arg.split(','); opts={'mods':parts[0],'key':parts[1]}
        if len(parts)>2 and parts[2]: opts['window']=parts[2]
        return call('send_shortcut',opts)
    if name=='exit': return call('exit')
    raise ValueError('Unsupported legacy dispatcher: '+name)

def keyword(name,arg):
    if name=='monitor':
        parts=[x.strip() for x in arg.split(',')]
        if parts[1]=='disable': opts={'output':parts[0],'disabled':True}
        else:
            opts=dict(zip(('output','mode','position','scale'),map(scalar,parts[:4])))
            for i in range(4,len(parts),2): opts[parts[i]]=scalar(parts[i+1])
        return 'hl.monitor('+lua(opts)+')'
    if name in ('windowrule','layerrule'):
        opts={}; match={}
        for part in arg.split(','):
            key,value=part.strip().split(' ',1)
            if key.startswith('match:'): match[key[6:]]=scalar(value)
            else: opts[key]=scalar(value)
        opts['match']=match
        return 'hl.'+('window_rule' if name=='windowrule' else 'layer_rule')+'('+lua(opts)+')'
    parts=name.split(':'); opts=scalar(arg)
    for key in reversed(parts): opts={key:opts}
    return 'hl.config('+lua(opts)+')'

def translate(command):
    kind,_,rest=command.partition(' '); name,_,arg=rest.strip().partition(' ')
    if kind=='dispatch': return dispatcher(name,arg)
    if kind=='keyword': return keyword(name,arg)
    raise ValueError('Unsupported mixed batch command: '+kind)

def main():
    args=sys.argv[1:]
    if '--batch' in args:
        i=args.index('--batch'); batch=' '.join(args[i+1:]); chunks=re.split(r';\s*(?=(?:dispatch|keyword)\s)',batch)
        if all(c.strip().startswith(('dispatch ','keyword ')) for c in chunks):
            args=args[:i]+['eval','; '.join(translate(c.strip()) for c in chunks)]
    else:
        for i,a in enumerate(args):
            if a in ('dispatch','keyword') and i+1<len(args):
                # Already-modern Lua dispatch goes directly to Hyprland.
                if a=='dispatch' and args[i+1].startswith('hl.'): break
                args=args[:i]+['eval',translate(' '.join(args[i:]))]; break
    if '-j' in args and any(a in args for a in ('clients','monitors','workspaces','activeworkspace','activewindow')):
        result=subprocess.run([REAL,*args],capture_output=True,text=True)
        def ids(node):
            if isinstance(node,list):
                for item in node: ids(item)
            elif isinstance(node,dict):
                if 'id' not in node and 'address' in node and 'type' in node and 'name' in node:
                    node['id'] = -(1000 + zlib.crc32(node['name'].encode())) if node['type']=='special' else 0
                for value in list(node.values()): ids(value)
        if result.returncode == 0:
            try:
                data=json.loads(result.stdout); ids(data); print(json.dumps(data)); return
            except json.JSONDecodeError: pass
        sys.stdout.write(result.stdout); sys.stderr.write(result.stderr); sys.exit(result.returncode)
    os.execv(REAL,[REAL,*args])
if __name__=='__main__':
    try: main()
    except (ValueError,IndexError) as e:
        print('hyprctl compatibility: '+str(e),file=sys.stderr); sys.exit(1)
