"""Manual GUI regression: opens test MPV windows; requires Hyprland and wtype.
Run with --legacy to reproduce the former MPV-owned-child failure.
"""
import os,sys,json,tempfile,subprocess,time,signal
from pathlib import Path
from unittest.mock import patch
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
MPV_SCRIPTS=Path(__file__).resolve().parents[2]/'mpv/.config/mpv/scripts'
sys.path.insert(0,str(SCRIPTS))
import stream_preview as preview
from mpv_clip import Player
legacy='--legacy' in sys.argv
service=os.environ.get('TEST_SERVICE','Twitch')
def wait_for(fn,seconds=4):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  value=fn()
  if value:return value
  time.sleep(.025)
 raise AssertionError('Timed out')
def layers():
 data=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','layers']))
 return [layer for m in data.values() for group in m['levels'].values() for layer in group if layer['namespace']=='stream-sidebar']
with tempfile.TemporaryDirectory(dir=preview.ROOT) as tmp:
 root=Path(tmp);ps=[];sidebar_pid=None
 try:
  script=MPV_SCRIPTS/'stream-sidebar.lua'
  if legacy:
   patched=root/'legacy-sidebar.lua';patched.write_text(script.read_text().replace(',detach=true','').replace('capture_stdout=false,capture_stderr=false','capture_stdout=true,capture_stderr=true'));script=patched
  for name in ('old','new'):
   endpoint=str(root/(name+'.sock'))
   args=['mpv','--no-config','--load-scripts=no','--vo=gpu','--gpu-api=opengl','--ao=null','--mute=yes','--idle=yes','--force-window=immediate','--input-ipc-server='+endpoint,'--wayland-app-id='+('mpv' if name=='old' else 'stream-preview'), '--script='+str(MPV_SCRIPTS/'pip-fullscreen.lua')]
   if name=='old':args+=['--script='+str(script)]
   else:args+=['--script='+str(SCRIPTS/'stream-preview.lua')]
   p=subprocess.Popen([*args,'av://lavfi:testsrc=size=320x180:rate=30'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);ps.append(p)
   wait_for(lambda:Path(endpoint).exists())
  old,new=ps
  wait_for(lambda:len([c for c in preview.clients() if c['pid'] in (old.pid,new.pid)])==2)
  a=Player(str(root/'old.sock'),old.pid);b=Player(str(root/'new.sock'),new.pid)
  for player in (a,b):
   player.command('set_property','user-data/stream-service',os.environ.get('TEST_FROM',service) if player is a else service);player.command('set_property','user-data/stream-name','test')
  a.command('set_property','fullscreen',True)
  wait_for(lambda:any(c['pid']==old.pid and c['fullscreen']==2 for c in preview.clients()))
  time.sleep(.1);a.command('keypress','TAB')
  wait_for(lambda:a.get('user-data/stream-sidebar-open'))
  sidebar_pid=int((Path(os.environ['XDG_RUNTIME_DIR'])/'stream-sidebar.lock').read_text())
  wait_for(layers)
  b.command('set_property','user-data/preview-ready',True)
  handoff=root/'handoff';session=root/'session';session.write_text('test')
  handoff.write_text(json.dumps(dict(pid=new.pid,endpoint=str(root/'new.sock'),name='test',service=service,created=time.time(),staged=True)))
  actual_clients=preview.clients
  def clients():return [c for c in actual_clients() if c['pid'] in (old.pid,new.pid)]
  with patch.object(preview,'HANDOFF',handoff),patch.object(preview,'SESSION',session),patch.object(preview,'CANONICAL',root/'canonical'),patch.object(preview,'clients',side_effect=clients):
   assert preview.adopt('test','Test','',service,'test','')==new.pid
  time.sleep(.6)
  alive=Path(f'/proc/{sidebar_pid}').exists();visible=bool(layers());margin=b.get('video-margin-ratio-left')
  print(('OLD' if legacy else 'FIXED'),'MPV-owned launch:', 'sidebar alive',alive,'visible',visible,'left margin',margin,flush=True)
  if legacy:
   assert not visible and margin>0,'Original failure did not reproduce'
  else:
   assert alive and visible
   assert old.poll() is not None
   subprocess.run(['wtype','f'],check=True)
   wait_for(lambda:b.get('fullscreen') is False)
   wait_for(lambda:not layers())
   wait_for(lambda:any(c['pid']==new.pid and c.get('pinned') for c in clients()))
   assert len(clients())==1
   b.command('keypress','f')
   wait_for(lambda:b.get('fullscreen') is True)
   wait_for(layers)
   subprocess.run(['wtype','-k','Tab'],check=True)
   wait_for(lambda:not layers())
   wait_for(lambda:b.get('video-margin-ratio-left')==0)
   print(service+': actual Tab launch, handoff, physical F, fullscreen return and Tab close PASS',flush=True)
  a.close();b.close()
 finally:
  for p in ps:
   if p.poll() is None:p.terminate()
  for p in ps:
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:p.kill()
  if sidebar_pid:
   try:os.kill(sidebar_pid,signal.SIGTERM)
   except ProcessLookupError:pass
