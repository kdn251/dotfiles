"""Receive remote attention events and match direct SSH TCP connections to Kitty."""
import ipaddress, json, logging, os, pathlib, re, select, shlex, socket, subprocess, time

def command(host):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*',host):raise ValueError('Invalid SSH alias')
    return ['ssh','-T','-S','none','-o','BatchMode=yes','-o','ClearAllForwardings=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',host,'python3 "$HOME/.local/share/agent-attention-ssh/ssh_remote.py" watch']

def watch(endpoint,inbox):
    host=endpoint['host']
    while True:
        proc=None
        try:
            proc=subprocess.Popen(command(host),stdout=subprocess.PIPE)
            buf=b'';last=time.monotonic()
            while True:
                if time.monotonic()-last>20:raise RuntimeError('SSH attention heartbeat timeout')
                if not select.select([proc.stdout],[],[],1)[0]:continue
                chunk=os.read(proc.stdout.fileno(),65536)
                if not chunk:raise RuntimeError('SSH event stream closed')
                buf+=chunk
                if len(buf)>1024*1024:raise RuntimeError('Oversized event stream')
                while b'\n' in buf:
                    line,buf=buf.split(b'\n',1);item=json.loads(line);last=time.monotonic()
                    if item.get('ready'):logging.info('Standalone SSH observer connected: %s',host)
                    event=item.get('event')
                    if not event:continue
                    if event.get('source') not in ('Claude','Codex'):continue
                    route={'host':host,'connection':event['connection']}
                    inbox.put({'source':event['source'],'session':host+':'+event['session'],'event':event['event'],'name':host+' · '+event['name'],'ssh_route':route,'probe':bool(event.get('probe'))})
        except Exception as exc:logging.warning('Standalone SSH observer reconnecting (%s): %s',host,exc)
        finally:
            if proc:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
        time.sleep(5)

def address(value):
    encoded,port=value.rsplit(':',1);raw=bytes.fromhex(encoded)
    # Linux proc encodes each 32-bit word in native endian order (x86 Linux here).
    if len(raw)==4:raw=raw[::-1];family=socket.AF_INET
    else:raw=b''.join(raw[i:i+4][::-1] for i in range(0,16,4));family=socket.AF_INET6
    ip=ipaddress.ip_address(socket.inet_ntop(family,raw))
    if isinstance(ip,ipaddress.IPv6Address) and ip.ipv4_mapped:ip=ip.ipv4_mapped
    return str(ip),int(port,16)

def connection_inodes(connection):
    if len(connection)!=4:return set()
    try:
        local=(str(ipaddress.ip_address(connection[0])),int(connection[1]));remote=(str(ipaddress.ip_address(connection[2])),int(connection[3]))
    except (ValueError,TypeError):return set()
    found=set()
    for path in (pathlib.Path('/proc/net/tcp'),pathlib.Path('/proc/net/tcp6')):
        try:lines=path.read_text().splitlines()[1:]
        except OSError:continue
        for line in lines:
            fields=line.split()
            if fields[3]=='01' and address(fields[1])==local and address(fields[2])==remote:found.add(fields[9])
    return found

def resolve(route,process_target,endpoints):
    if not any(e.get('enabled',True) and e['host']==route.get('host') for e in endpoints):return None
    inodes=connection_inodes(route.get('connection',[]))
    if not inodes:return None
    candidates={}
    for p in pathlib.Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if (p/'comm').read_text().strip()!='ssh':continue
            args=(p/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
            # A multiplexed master has no unique channel->window mapping; never guess.
            if '[mux]' in ' '.join(args):continue
            owned={os.readlink(fd)[8:-1] for fd in (p/'fd').iterdir() if os.readlink(fd).startswith('socket:[')}
            if not owned.intersection(inodes):continue
            # A live ControlMaster socket can serve multiple terminal channels.
            # Even its first attached session is ambiguous once reuse is possible.
            unix = pathlib.Path('/proc/net/unix').read_text().splitlines()[1:]
            listeners = {line.split()[6] for line in unix if line.split()[3]=='00010000'}
            if owned.intersection(listeners):continue
            env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode().split('\0') if '=' in x)
            target=process_target(int(p.name),env.get('KITTY_WINDOW_ID'))
            if target:candidates[(target['address'],target.get('kitty_id'))]=target
        except (OSError,ValueError,UnicodeError):continue
    return next(iter(candidates.values())) if len(candidates)==1 else None
