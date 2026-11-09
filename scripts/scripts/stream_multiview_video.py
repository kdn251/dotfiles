"""Embedded video with shared playback controls and a private per-pane IPC socket."""
import ctypes as C
import locale
from pathlib import Path
import threading
import os
import uuid
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib

lib=C.CDLL('libmpv.so.2')
GL=C.CDLL('libGL.so.1')
EGL=C.CDLL('libEGL.so.1')
P=C.c_void_p
class Param(C.Structure):_fields_=[('type',C.c_int),('data',P)]
GET=C.CFUNCTYPE(P,P,C.c_char_p)
UPDATE=C.CFUNCTYPE(None,P)
class Init(C.Structure):_fields_=[('get_proc',GET),('ctx',P)]
class FBO(C.Structure):_fields_=[('fbo',C.c_int),('w',C.c_int),('h',C.c_int),('format',C.c_int)]
for name,args,result in [
 ('mpv_create',[],P),('mpv_initialize',[P],C.c_int),
 ('mpv_set_option_string',[P,C.c_char_p,C.c_char_p],C.c_int),
 ('mpv_set_property_string',[P,C.c_char_p,C.c_char_p],C.c_int),
 ('mpv_get_property_string',[P,C.c_char_p],P),('mpv_free',[P],None),
 ('mpv_command',[P,C.POINTER(C.c_char_p)],C.c_int),
 ('mpv_render_context_create',[C.POINTER(P),P,C.POINTER(Param)],C.c_int),
 ('mpv_render_context_set_update_callback',[P,UPDATE,P],None),
 ('mpv_render_context_render',[P,C.POINTER(Param)],C.c_int),
 ('mpv_render_context_free',[P],None),('mpv_terminate_destroy',[P],None)]:
    fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
EGL.eglGetProcAddress.argtypes=[C.c_char_p];EGL.eglGetProcAddress.restype=P
GL.glGetIntegerv.argtypes=[C.c_uint,C.POINTER(C.c_int)]


def pointer(value):return C.cast(C.pointer(value),P)


def shared_osc_options(path=None):
    """Use the normal OSC sizing without loading global window/IPC settings."""
    path=path or Path.home()/'.config/mpv/script-opts/osc.conf'
    values={}
    try:lines=path.read_text().splitlines()
    except OSError:return ''
    for line in lines:
        key,separator,value=line.partition('=')
        key=key.strip();value=value.split('#',1)[0].strip()
        if separator and key in ('scalewindowed','scalefullscreen','scaleforcedwindow','vidscale'):
            values['osc-'+key]=value
    return ','.join(key+'='+value for key,value in values.items())


class Video(Gtk.GLArea):
    def __init__(self,ready):
        super().__init__()
        self.ready=ready;self.loaded=False;self.closed=False;self.context=P();self.pending_url=None
        # GTK initializes the user's locale; libmpv aborts unless numeric
        # parsing uses C. Set this after widget/GTK initialization, not at import.
        locale.setlocale(locale.LC_NUMERIC,'C')
        self.handle=lib.mpv_create()
        if not self.handle:raise RuntimeError('Could not create video player')
        runtime=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'stream-multiview'
        runtime.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.endpoint=runtime/f'video-{uuid.uuid4().hex}.ipc'
        options={'script-opts':shared_osc_options(),
                 'input-conf':str(Path.home()/'.config/mpv/input.conf'),
                 'input-ipc-server':str(self.endpoint),
                 'screenshot-directory':str(Path.home()/'pictures/screenshots/mpv'),
                 'config':'no','load-scripts':'no','vo':'libmpv','hwdec':'auto-safe',
                 'osc':'no','idle':'yes','terminal':'no','mute':'yes','cache':'yes','cache-secs':'15',
                 'demuxer-max-bytes':'128MiB','demuxer-max-back-bytes':'200MiB',
                 'user-agent':'Mozilla/5.0','ytdl':'yes'}
        for key,value in options.items():lib.mpv_set_option_string(self.handle,key.encode(),value.encode())
        if lib.mpv_initialize(self.handle)<0:raise RuntimeError('Could not initialize video renderer')
        self.command('load-script',str(Path.home()/'.config/mpv/scripts/osc.lua'))
        self.command('load-script',str(Path.home()/'scripts/stream-live-seek.lua'))
        for script in ('screenshot-copy.lua','clip-menu.lua','copy-url.lua'):
            self.command('load-script',str(Path.home()/'.config/mpv/scripts'/script))
        self.set_required_version(3,2);self.set_auto_render(False)
        self.set_hexpand(True);self.set_vexpand(True)
        self.connect('realize',self.realize_video);self.connect('render',self.render_video)
        self.get_proc=GET(lambda ctx,name:EGL.eglGetProcAddress(name))
        self.update=UPDATE(lambda ctx:self.request_render())
        self.queued=False
        self.poll=GLib.timeout_add(200,self.check_ready)

    def get(self,key):
        raw=lib.mpv_get_property_string(self.handle,key.encode())
        if not raw:return ''
        try:return C.string_at(raw).decode(errors='replace')
        finally:lib.mpv_free(raw)

    def set(self,key,value):
        if not self.closed:lib.mpv_set_property_string(self.handle,key.encode(),str(value).encode())

    def command(self,*args):
        values=(C.c_char_p*(len(args)+1))(*(str(v).encode() for v in args),None)
        if lib.mpv_command(self.handle,values)<0:raise RuntimeError('Video command failed')

    def realize_video(self,*_):
        self.make_current()
        if self.get_error():raise RuntimeError(str(self.get_error()))
        init=Init(self.get_proc,None);api=C.create_string_buffer(b'opengl')
        params=(Param*3)(Param(1,C.cast(api,P)),Param(2,pointer(init)),Param())
        if lib.mpv_render_context_create(C.byref(self.context),self.handle,params)<0:
            raise RuntimeError('Could not create video rendering context')
        lib.mpv_render_context_set_update_callback(self.context,self.update,None)
        if self.pending_url:self.command('loadfile',self.pending_url,'replace');self.pending_url=None

    def request_render(self):
        if self.closed or self.queued:return
        self.queued=True
        GLib.idle_add(self.queue_frame)

    def queue_frame(self):
        self.queued=False
        if not self.closed:self.queue_render()
        return False

    def render_video(self,*_):
        if self.closed or not self.context:return True
        fbo=C.c_int();GL.glGetIntegerv(0x8CA6,C.byref(fbo))
        scale=self.get_scale_factor();target=FBO(fbo.value,self.get_allocated_width()*scale,self.get_allocated_height()*scale,0)
        flip=C.c_int(1)
        params=(Param*3)(Param(3,pointer(target)),Param(4,pointer(flip)),Param())
        lib.mpv_render_context_render(self.context,params)
        return True

    def load(self,url,service):
        self.loaded=False
        self.set('referrer','https://'+service.lower()+'.com/' if service in ('Kick','Rumble') else '')
        if self.context:self.command('loadfile',url,'replace')
        else:self.pending_url=url

    def check_ready(self):
        if self.closed:return False
        if not self.loaded and self.get('video-params/w'):
            self.loaded=True;self.ready()
        return True

    def close(self):
        if self.closed:return
        self.closed=True
        self.endpoint.unlink(missing_ok=True)
        GLib.source_remove(self.poll)
        if self.context:
            self.make_current()
            lib.mpv_render_context_free(self.context);self.context=P()
        handle=self.handle
        threading.Thread(target=lambda:lib.mpv_terminate_destroy(handle),daemon=True).start()
