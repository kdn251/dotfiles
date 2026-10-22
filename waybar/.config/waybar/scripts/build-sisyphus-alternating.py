#!/usr/bin/env python3
"""Painted cutout gait: independently solved near/far legs, exactly half a cycle apart."""
from pathlib import Path
import math,sys,json,cairo
from PIL import Image
BASE=Path(__file__).resolve().parent.parent/'assets/sisyphus-studies'
OUT=BASE/'stride-v4';N=96
rig=cairo.ImageSurface.create_from_png(str(OUT/'rig-source.png'))
rock_path=BASE/'rolling-v2/boulder.png';rock=cairo.ImageSurface.create_from_png(str(rock_path))
im=Image.open(rock_path);alpha=im.getchannel('A');x0,y0,x1,y1=alpha.point(lambda x:255 if x>128 else 0).getbbox()
mx=(x0+x1)/2;my=(y0+y1)/2;rs=200/max(x1-x0,y1-y0)
outline=[]
for y in range(y0,y1,8):
 xs=[x for x in range(x0,x1,4) if alpha.getpixel((x,y))>128]
 if xs:outline.extend([((min(xs)-mx)*rs,(y-my)*rs),((max(xs)-mx)*rs,(y-my)*rs)])
ground=cairo.ImageSurface.create_from_png(str(BASE/'rolling-v2/person-0.png'))
# Source coordinates and anatomical pivots, all in the unchanged generated atlas.
PARTS={
 'near_thigh':((765,65,975,464),(840,123),(905,409)),
 'far_thigh':((180,520,405,945),(258,585),(330,877)),
 'near_shin':((1150,65,1340,401),(1265,126),(1236,384)),
 'far_shin':((630,510,790,863),(724,569),(700,846)),
 'near_foot':((1150,359,1410,485),(1236,384),(1336,384)),
 'far_foot':((620,823,900,970),(700,846),(800,846)),
}
def cut(c,rect):
 x0,y0,x1,y1=rect;c.rectangle(x0,y0,x1-x0,y1-y0);c.clip();c.set_source_surface(rig,0,0);c.paint()
def bone(c,name,start,end,width=1):
 rect,a,b=PARTS[name];sx,sy=b[0]-a[0],b[1]-a[1];dx,dy=end[0]-start[0],end[1]-start[1]
 ratio=math.hypot(dx,dy)/math.hypot(sx,sy)
 c.save();c.translate(*start);c.rotate(math.atan2(dy,dx)-math.atan2(sy,sx));c.scale(ratio*width,ratio);c.translate(-a[0],-a[1]);cut(c,rect);c.restore()
def solve(hip,foot,l1=63,l2=66):
 dx,dy=foot[0]-hip[0],foot[1]-hip[1];d=math.hypot(dx,dy)
 assert 1<d<l1+l2,(hip,foot,d)
 along=(l1*l1-l2*l2+d*d)/(2*d);side=math.sqrt(max(0,l1*l1-along*along))
 return hip[0]+dx/d*along+dy/d*side,hip[1]+dy/d*along-dx/d*side
VARIANTS={'a':(65,23,.53),'b':(72,30,.54),'c':(60,34,.51)}
def foot_at(p,stride,lift,stance):
 if p<stance:
  t=p/stance;x=210+stride-2*stride*t;h=0
 else:
  t=(p-stance)/(1-stance);s=t*t*(3-2*t);x=210-stride+2*stride*s;h=lift*math.sin(math.pi*t)
 return (x,310-.18*x-18-h)
def render(style,i,w):
 stride,lift,stance=VARIANTS[style];phase=(i*2/N)%1
 bob=2.5*math.cos(phase*math.tau*2)
 hip=(217,148+bob)
 feet={side:foot_at((phase+offset)%1,stride,lift,stance) for side,offset in [('near',0),('far',.5)]}
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w,w//2);c=cairo.Context(surface);c.scale(w/628,w/628)
 c.save();c.move_to(0,310);c.line_to(628,197);c.line_to(628,314);c.line_to(0,314);c.close_path();c.clip();c.set_source_surface(ground,0,-11);c.paint();c.restore()
 angle=i*math.tau/N;rot=[(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)) for x,y in outline]
 cx=480;cy=310-.18*cx-max(y+.18*x for x,y in rot)
 c.save();c.translate(cx,cy);c.rotate(angle);c.scale(rs,rs);c.set_source_surface(rock,-mx,-my);c.paint();c.restore()
 for side in ('far','near'):
  c.push_group()
  foot=feet[side];h=(hip[0]-(4 if side=='far' else 0),hip[1]);knee=solve(h,foot,70+(stride-65)*.5,73+(stride-65)*.5)
  bone(c,side+'_shin',knee,foot)
  bone(c,side+'_thigh',h,knee)
  # Sandals stay parallel to the slope, independent of shin rotation.
  c.save();c.translate(*foot);c.rotate(-math.atan(.18));c.scale(.235,.235);a=PARTS[side+'_foot'][1];c.translate(-a[0],-a[1]);cut(c,PARTS[side+'_foot'][0]);c.restore()
  layer=c.pop_group();c.set_source(layer);c.paint()
  if side=='far':
   c.set_source_rgba(.12,.10,.09,.24);c.mask(layer)
 # Pivot the detailed torso about its palms: shoulders/hips work against the stone.
 c.save();c.translate(395,104);c.rotate(.19+.012*math.sin(phase*math.tau*2));c.scale(.365,.365);c.translate(-687,-185);cut(c,(60,5,720,505));c.restore()
 return surface,feet
if __name__=='__main__':
 width=628 if '--large' in sys.argv else 160
 checks=[]
 for style in VARIANTS:
  target=OUT/style;target.mkdir(exist_ok=True)
  for i in range(N):
   s,feet=render(style,i,width);s.write_to_png(str(target/f'frame-{i:03}.png'))
   if i%6==0:checks.append({'variant':style,'frame':i,'near':feet['near'],'far':feet['far']})
 (OUT/'foot-positions.json').write_text(json.dumps(checks,indent=2)+'\n')
 print('Rendered three alternating gait variants:',width,'px,',N,'frames each')
