"""Read reader-owned positions; publish book progress without changing bookmarks."""
from contextlib import closing
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
from urllib.parse import quote, unquote, urlparse
from newsboat_media import atomic_write

DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/books'


def load(path, default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default


def foliate_positions():
    result={}
    roots=[DATA/'com.github.johnfactotum.Foliate',Path.home()/'.var/app/com.github.johnfactotum.Foliate/data/com.github.johnfactotum.Foliate']
    for root in roots:
        for ident,uri in load(root/'library/uri-store.json',{}).get('uris',[]):
            if uri.startswith('file:'):path=Path(unquote(urlparse(uri).path))
            elif uri.startswith(('~/','/')):path=Path(uri).expanduser()
            else:continue
            data=load(root/(quote(ident,safe="~()*!.'-")+'.json'),{})
            progress=data.get('progress',[])
            if len(progress)==2 and all(isinstance(x,(int,float)) for x in progress) and progress[1]>0:
                result[path.resolve().as_uri()]=progress[0]/progress[1]
    return result


def pdf_positions(urls):
    result={}
    cache=load(STATE/'pdf-pages.json',{})
    db=DATA/'zathura/bookmarks.sqlite'
    if db.exists():
        try:
            with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=.2)) as con:
                rows=con.execute('SELECT file,page FROM fileinfo').fetchall()
            for filename,page in rows:
                path=Path(filename)
                if path.resolve().as_uri() not in urls or path.suffix.lower()!='.pdf' or not path.is_file():continue
                stat=path.stat();signature=[stat.st_size,stat.st_mtime_ns]
                entry=cache.get(filename,{})
                if entry.get('signature')!=signature:
                    output=subprocess.run(['pdfinfo',str(path)],capture_output=True,text=True,timeout=3)
                    pages=next((int(line.split(':',1)[1]) for line in output.stdout.splitlines() if line.startswith('Pages:')),0)
                    entry=dict(signature=signature,pages=pages);cache[filename]=entry
                pages=entry.get('pages',0)
                if pages:result[path.resolve().as_uri()]=page/max(1,pages-1)
        except (OSError,ValueError,sqlite3.Error,subprocess.TimeoutExpired):pass
    # Zathura saves its database on close. Read live page numbers over D-Bus too.
    try:
        from gi.repository import Gio,GLib
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        def call(dest,path,interface,method,args=None):
            return bus.call_sync(dest,path,interface,method,args,None,Gio.DBusCallFlags.NONE,500,None).unpack()
        names=call('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','ListNames')[0]
        for name in names:
            if not name.startswith('org.pwmt.zathura.PID-'):continue
            try:
                props=call(name,'/org/pwmt/zathura','org.freedesktop.DBus.Properties','GetAll',GLib.Variant('(s)',('org.pwmt.zathura',)))[0]
                filename=props.get('filename','');pages=props.get('numberofpages',0)
                if filename and pages and Path(filename).resolve().as_uri() in urls:
                    result[Path(filename).resolve().as_uri()]=props['pagenumber']/max(1,pages-1)
            except GLib.Error:continue
    except (ImportError,ValueError,OSError):pass
    except Exception:pass  # D-Bus can disappear while logging out.
    if cache and load(STATE/'pdf-pages.json',{})!=cache:atomic_write(STATE/'pdf-pages.json',json.dumps(cache))
    return result


def publish(rows, refresh=True):
    saved=load(STATE/'progress.json',{})
    current={}
    if refresh:
        current.update(pdf_positions({row['url'] for row in rows}));current.update(foliate_positions())
    for row in rows:
        url=row['url'];value=current.get(url,0)
        if isinstance(value,(int,float)) and math.isfinite(value):
            saved[url]=max(saved.get(url,0),min(1,max(0,value)))
    text=json.dumps(saved,sort_keys=True)
    if load(STATE/'progress.json',{})!=saved:atomic_write(STATE/'progress.json',text)
    lines=''.join(f"{row['url']}\t{int(saved.get(row['url'],0)*100)}%\n" for row in rows)
    target=STATE/'status.tsv.read'
    if not target.exists() or target.read_text()!=lines:atomic_write(target,lines)
