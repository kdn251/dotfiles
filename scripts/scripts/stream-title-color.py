#!/usr/bin/env python3
"""Render a cached MPV title strip with Apple color emoji for overlay-add."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from PIL import Image,ImageDraw,ImageFont

APPLE=Path.home()/'.local/share/mpv/fonts/AppleColorEmoji.ttf'
# Font source: https://github.com/samuelngs/apple-emoji-ttf/releases/tag/macos-26-20260722-484daf4e

def emoji(c):
    n=ord(c)
    return 0x1f000<=n<=0x1faff or 0x2600<=n<=0x27bf or n in (0xfe0f,0x200d,0x20e3)

def runs(text):
    result=[]
    # Selectors/joiners are modifiers, not independent glyphs. In titles they
    # sometimes follow a space; sending that isolated run to libraqm fails.
    tokens=re.findall(r'[0-9#*]\ufe0f?\u20e3|.',text,flags=re.S)
    for i,c in enumerate(tokens):
        if c in ('\ufe0f','\ufe0e','\u20e3','\u200d'):
            if not result or not result[-1][0]:continue
            if c=='\u200d' and (i+1==len(tokens) or not emoji(tokens[i+1][0])):continue
            result[-1]=(True,result[-1][1]+c)
            continue
        kind=len(c)>1 or emoji(c)
        if result and result[-1][0]==kind:result[-1]=(kind,result[-1][1]+c)
        else:result.append((kind,c))
    return result

def render(text,family):
    fontpath=subprocess.check_output(['fc-match','-f','%{file}',family],text=True).strip()
    key=hashlib.sha256((text+fontpath+str(APPLE.stat().st_mtime_ns)+'-v2').encode()).hexdigest()
    root=Path.home()/'.cache/mpv-stream-title-color';root.mkdir(parents=True,exist_ok=True)
    meta=root/(key+'.json');target=root/(key+'.bgra')
    if meta.exists() and target.exists():return json.loads(meta.read_text())
    fonts=[ImageFont.truetype(fontpath,40),ImageFont.truetype(str(APPLE),40)]
    pieces=[(fonts[kind],value,kind) for kind,value in runs(text[:5000])]
    width=max(1,int(sum(f.getlength(t) for f,t,_ in pieces)+2));height=56
    im=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(im);x=0
    for font,value,color in pieces:
        draw.text((x,42),value,font=font,fill='white',anchor='ls',embedded_color=color)
        x+=font.getlength(value)
    # MPV's bitmap overlays use premultiplied BGRA.
    raw=bytearray(im.tobytes())
    for i in range(0,len(raw),4):
        r,g,b,a=raw[i:i+4];raw[i:i+4]=bytes((b*a//255,g*a//255,r*a//255,a))
    with tempfile.NamedTemporaryFile(dir=root,delete=False) as out:
        out.write(raw);tmp=Path(out.name)
    tmp.replace(target)
    data={'path':str(target),'width':width,'height':height,'font_size':40}
    meta.write_text(json.dumps(data));return data
if __name__=='__main__':
    try:print(json.dumps(render(sys.argv[1],sys.argv[2])))
    except (OSError,ValueError,subprocess.SubprocessError):sys.exit(1)
