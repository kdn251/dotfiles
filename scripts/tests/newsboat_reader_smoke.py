"""Run under xvfb-run and dbus-run-session with isolated XDG directories; pass a scratch directory."""
import os,sys,time,subprocess,json,sqlite3,zipfile
from pathlib import Path
from gi.repository import Gio,GLib
root=Path(sys.argv[1]);root.mkdir(exist_ok=True)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import newsboat_books_progress as progress
# Five-page synthetic PDF, no personal documents.
objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R 9 0 R 11 0 R] /Count 5 >>']
for i in range(5):
 objects += [f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Contents {4+2*i} 0 R >>','<< /Length 0 >>\nstream\n\nendstream']
data=b'%PDF-1.4\n';offsets=[]
for i,obj in enumerate(objects,1):offsets.append(len(data));data+=f'{i} 0 obj\n{obj}\nendobj\n'.encode()
xref=len(data);data+=f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()+b''.join(f'{o:010} 00000 n \n'.encode() for o in offsets)+f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
pdf=root/'sample.pdf';pdf.write_bytes(data)
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def call(pid,method,args=None,interface='org.pwmt.zathura'):
 return bus.call_sync('org.pwmt.zathura.PID-'+str(pid),'/org/pwmt/zathura',interface,method,args,None,Gio.DBusCallFlags.NONE,1000,None).unpack()
def wait(fn,timeout=15):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   value=fn()
   if value:return value
  except Exception:pass
  time.sleep(.2)
 raise AssertionError('Timed out')
with (root/'reader.log').open('w') as log:
 for attempt in range(2):
  p=subprocess.Popen(['zathura',str(pdf)],stdout=log,stderr=log)
  try:
   props=lambda:call(p.pid,'GetAll',GLib.Variant('(s)',('org.pwmt.zathura',)),'org.freedesktop.DBus.Properties')[0]
   wait(lambda:props().get('numberofpages')==5)
   if attempt==0:
    call(p.pid,'GotoPage',GLib.Variant('(u)',(2,)))
    wait(lambda:props()['pagenumber']==2)
    progress.publish([{'url':pdf.as_uri()}])
    assert '50%' in (progress.STATE/'status.tsv.read').read_text()
   else:assert props()['pagenumber']==2,props()
   call(p.pid,'ExecuteCommand',GLib.Variant('(s)',('quit',)))
   p.wait(timeout=8)
  finally:
   if p.poll() is None:p.terminate();p.wait()
 print('PDF: live 50% and page 3 restored',flush=True)
 epub=root/'sample.epub'
 with zipfile.ZipFile(epub,'w') as z:
  z.writestr('mimetype','application/epub+zip')
  z.writestr('META-INF/container.xml','<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
  z.writestr('content.opf','<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">newsboat-reader-test</dc:identifier><dc:title>Newsboat Test Book</dc:title><dc:language>en</dc:language></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>')
  z.writestr('chapter.xhtml','<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Test</title></head><body>'+''.join(f'<p>Paragraph {i}. '+('A sample book for testing reading position. '*20)+'</p>' for i in range(150))+'</body></html>')
 location=None
 for attempt in range(2):
  p=subprocess.Popen(['foliate',str(epub)],stdout=log,stderr=log)
  try:
   state=progress.DATA/'com.github.johnfactotum.Foliate/newsboat-reader-test.json'
   wait(lambda:state.exists())
   wid=wait(lambda:subprocess.check_output(['xdotool','search','--name','Newsboat Test Book'],text=True).strip().splitlines()[-1])
   time.sleep(2)
   if attempt==0:
    subprocess.run(['xdotool','windowfocus',wid,'key','--clearmodifiers','--delay','300','Right','Right','Right','Right','Right'],check=True)
    wait(lambda:progress.foliate_positions().get(epub.as_uri(),0)>0)
    time.sleep(2);location=json.loads(state.read_text())['lastLocation']
    progress.publish([{'url':epub.as_uri()}]);print('EPUB progress:',progress.foliate_positions()[epub.as_uri()],flush=True)
   else:
    time.sleep(2);assert json.loads(state.read_text())['lastLocation']==location
   subprocess.run(['xdotool','windowfocus',wid,'key','ctrl+w'],check=True)
   p.wait(timeout=8)
  finally:
   if p.poll() is None:p.terminate();p.wait()
 print('EPUB: progress and saved reading location restored',flush=True)
