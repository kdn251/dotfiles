#!/usr/bin/env python3
"""Composite extracted illustration layers into a seamless rolling study.
Approved painted/ files are read-only and never overwritten.
"""
from pathlib import Path
import math,cairo,sys
from PIL import Image
BASE=Path(__file__).resolve().parent.parent/'assets/sisyphus-studies/rolling-v2'
N=96
people=[cairo.ImageSurface.create_from_png(str(BASE/f'person-{i}.png')) for i in range(8)]
rock=cairo.ImageSurface.create_from_png(str(BASE/'boulder.png'))
im=Image.open(BASE/'boulder.png');alpha=im.getchannel('A');bbox=alpha.point(lambda x:255 if x>128 else 0).getbbox()
x0,y0,x1,y1=bbox;mx=(x0+x1)/2;my=(y0+y1)/2;scale=218/max(x1-x0,y1-y0)
points=[]
for y in range(y0,y1,8):
 xs=[x for x in range(x0,x1,4) if alpha.getpixel((x,y))>128]
 if xs:points.extend([((min(xs)-mx)*scale,(y-my)*scale),((max(xs)-mx)*scale,(y-my)*scale)])
for i in range(N):
 angle=i*math.tau/N
 rotated=[(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)) for x,y in points]
 # Match the bottom contact to a fixed inclined support line.
 cx=490
 cy=329-.18*cx-max(y+.18*x for x,y in rotated)
 width=628 if '--large' in sys.argv else 160
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,width//2);ctx=cairo.Context(surface);ctx.scale(width/628,width/628)
 person=people[(i//4)%8]
 ctx.set_source_surface(person,0,0);ctx.paint()
 ctx.save();ctx.translate(cx,cy);ctx.rotate(angle);ctx.scale(scale,scale)
 ctx.set_source_surface(rock,-mx,-my);ctx.paint();ctx.restore()
 # Fingers/forearms stay in front of the stone at the contact area.
 ctx.save();ctx.rectangle(320,40,95,140);ctx.clip();ctx.set_source_surface(person,0,0);ctx.paint();ctx.restore()
 surface.write_to_png(str(BASE/f'frame-{i:03}.png'))
print(f'Rendered {N} frames; full rotation every 3 seconds at 32 fps')
