#!/usr/bin/env python3
"""Articulated painted gait trials. Approved A and rolling-v2 stay untouched."""
from pathlib import Path
import math,cairo,sys,json
from PIL import Image
BASE=Path(__file__).resolve().parent.parent/'assets/sisyphus-studies'
OUT=BASE/'stride-v3'
N=96
scale=.70
people=[]
for i in range(8):
 path=OUT/f'person-{i}.png';im=Image.open(path);a=im.getchannel('A')
 bbox=a.point(lambda p:255 if p>150 else 0).getbbox()
 x0,y0,x1,y1=bbox
 tx=395-scale*x1
 support=max(y*scale+.18*(x*scale+tx) for y in range(y0,y1,2) for x in range(x0,x1,2) if a.getpixel((x,y))>150)
 ty=310-support
 people.append((cairo.ImageSurface.create_from_png(str(path)),tx,ty))
rock_path=BASE/'rolling-v2/boulder.png';rock=cairo.ImageSurface.create_from_png(str(rock_path))
im=Image.open(rock_path);alpha=im.getchannel('A');x0,y0,x1,y1=alpha.point(lambda x:255 if x>128 else 0).getbbox()
mx=(x0+x1)/2;my=(y0+y1)/2;rs=200/max(x1-x0,y1-y0)
points=[]
for y in range(y0,y1,8):
 xs=[x for x in range(x0,x1,4) if alpha.getpixel((x,y))>128]
 if xs:points.extend([((min(xs)-mx)*rs,(y-my)*rs),((max(xs)-mx)*rs,(y-my)*rs)])
ground=cairo.ImageSurface.create_from_png(str(BASE/'rolling-v2/person-0.png'))
for style,cycles in (('a',2),('b',3),('c',4)):
 out=OUT/style;out.mkdir(exist_ok=True)
 for i in range(N):
  angle=i*math.tau/N
  rotated=[(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)) for x,y in points]
  cx=480;cy=310-.18*cx-max(y+.18*x for x,y in rotated)
  w=628 if '--large' in sys.argv else 160
  surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w,w//2);c=cairo.Context(surface);c.scale(w/628,w/628)
  # Stable ground texture, clipped below the original feet so no old limbs remain.
  c.save();c.move_to(0,310);c.line_to(628,197);c.line_to(628,314);c.line_to(0,314);c.close_path();c.clip()
  c.set_source_surface(ground,0,-11);c.paint();c.restore()
  c.save();c.translate(cx,cy);c.rotate(angle);c.scale(rs,rs);c.set_source_surface(rock,-mx,-my);c.paint();c.restore()
  phase=(i*cycles/N)%1
  index=int(phase*8)%8
  person,tx,ty=people[index]
  c.save();c.translate(tx,ty);c.scale(scale,scale);c.set_source_surface(person,0,0);c.paint();c.restore()
  surface.write_to_png(str(out/f'frame-{i:03}.png'))
 print(f'{style}: {cycles} gait cycles per 3-second stone rotation')
(OUT/'registration.json').write_text(json.dumps([{'x':x,'y':y,'scale':scale} for _,x,y in people],indent=2)+'\n')
