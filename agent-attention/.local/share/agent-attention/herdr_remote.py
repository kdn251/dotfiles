"""Transient remote helper, sent through SSH; never installed on the server."""
import json, os, socket, sys, time

def request(path, method, params):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(5);sock.connect(os.path.expanduser(path))
        sock.sendall((json.dumps({'id':'agent-attention','method':method,'params':params})+'\n').encode())
        with sock.makefile('rb') as stream: reply=json.loads(stream.readline(4*1024*1024))
        if 'error' in reply:raise RuntimeError(reply['error'])
        return reply['result']

def matches(agent, expected):
    return (agent.get('agent')=='claude' and agent.get('pane_id')==expected['pane']
            and agent.get('terminal_id')==expected['terminal']
            and agent.get('agent_session',{}).get('value')==expected['session'])

def main(path, mode, expected=None):
    if mode=='focus':
        agents=request(path,'agent.list',{}).get('agents',[])
        if not any(matches(a,expected) for a in agents):raise RuntimeError('Remote pane no longer contains the expected Claude session')
        result=request(path,'agent.focus',{'target':expected['pane']})
        if not matches(result.get('agent',{}),expected):raise RuntimeError('Remote focus identity mismatch')
        print(json.dumps({'focused':True}),flush=True);return
    if mode!='watch':raise ValueError('Unknown mode')
    while True:
        agents=request(path,'agent.list',{}).get('agents',[])
        clean=[]
        for a in agents:
            if a.get('agent')!='claude':continue
            clean.append({k:a.get(k) for k in ['agent','agent_status','agent_session','pane_id','terminal_id','tab_id','workspace_id','completion_seq','terminal_title_stripped','cwd']})
        activity=[{k:a.get(k) for k in ('agent','agent_status','agent_session','pane_id','terminal_title_stripped','cwd')} for a in agents]
        print(json.dumps({'agents':clean,'activity':activity}),flush=True);time.sleep(2)

if __name__=='__main__':main(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]) if len(sys.argv)>3 else None)
