#!/usr/bin/env python3
"""Review-only anatomy repair: clean torso, two complete arms, continuous ankles."""
from pathlib import Path
import math,json,sys,cairo
from PIL import Image
BASE=Path(__file__).resolve().parent.parent/'assets/sisyphus-studies'
OUT=BASE/'anatomy-repair-v1';N=96;SLOPE=20/68;GROUND=345
load=lambda p:cairo.ImageSurface.create_from_png(str(p))
rig=load(BASE/'stride-v4/rig-source.png');torso=load(OUT/'torso.png');arms=load(OUT/'arm-parts.png')
rock_path=BASE/'rolling-v2/boulder.png';rock=load(rock_path)
im=Image.open(rock_path);alpha=im.getchannel('A');x0,y0,x1,y1=alpha.point(lambda x:255 if x>128 else 0).getbbox()
mx=(x0+x1)/2;my=(y0+y1)/2;rs=200/max(x1-x0,y1-y0)
left=[];right=[]
for y in range(y0,y1,8):
 xs=[x for x in range(x0,x1,4) if alpha.getpixel((x,y))>128]
 if xs:
  left.append(((min(xs)-mx)*rs,(y-my)*rs));right.append(((max(xs)-mx)*rs,(y-my)*rs))
polygon=left+right[::-1];ground=load(BASE/'rolling-v2/person-0.png')
def smooth(t):
 t=max(0,min(1,t));return t*t*(3-2*t)
def rotate(p,a):
 x,y=p;return (x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a))
def add(a,b):return (a[0]+b[0],a[1]+b[1])
def sub(a,b):return (a[0]-b[0],a[1]-b[1])
def rigid(source_anchor,target_anchor,angle,scale):
 def transform(p):
  x,y=rotate(sub(p,source_anchor),angle)
  return target_anchor[0]+scale*x,target_anchor[1]+scale*y
 return transform

def draw_mesh(c,source,bounds,warp,step=20,mask=None):
 x0,y0,x1,y1=bounds
 xs=list(range(x0,x1,step))+[x1];ys=list(range(y0,y1,step))+[y1]
 for y0,y1 in zip(ys,ys[1:]):
  for x0,x1 in zip(xs,xs[1:]):
   for src in (((x0,y0),(x1,y0),(x1,y1)),((x0,y0),(x1,y1),(x0,y1))):
    dst=[warp(p) for p in src];a,b,d=src;u,v,z=dst
    srcmat=cairo.Matrix(b[0]-a[0],b[1]-a[1],d[0]-a[0],d[1]-a[1],a[0],a[1]);srcmat.invert()
    dstmat=cairo.Matrix(v[0]-u[0],v[1]-u[1],z[0]-u[0],z[1]-u[1],u[0],u[1])
    transform=srcmat.multiply(dstmat)
    if abs(transform.xx*transform.yy-transform.xy*transform.yx)<1e-5:continue
    c.save();c.set_antialias(cairo.ANTIALIAS_NONE);c.move_to(*u);c.line_to(*v);c.line_to(*z);c.close_path();c.clip()
    c.transform(transform);c.set_source_surface(source,0,0);c.get_source().set_filter(cairo.FILTER_BILINEAR)
    if mask is None:c.paint()
    else:c.mask(mask)
    c.restore()
def draw_bone(c,source,bounds,a,b,u,v,fade_start=False):
 src=sub(b,a);dst=sub(v,u);scale=math.hypot(*dst)/math.hypot(*src);angle=math.atan2(dst[1],dst[0])-math.atan2(src[1],src[0])
 c.save();c.translate(*u);c.rotate(angle);c.scale(scale,scale);c.translate(-a[0],-a[1]);x0,y0,x1,y1=bounds;c.rectangle(x0,y0,x1-x0,y1-y0);c.clip();c.set_source_surface(source,0,0)
 if fade_start:
  fade=cairo.LinearGradient(a[0],a[1],a[0]+.30*src[0],a[1]+.30*src[1]);fade.add_color_stop_rgba(0,1,1,1,0);fade.add_color_stop_rgba(1,1,1,1,1);c.mask(fade)
 else:c.paint()
 c.restore()
def joint(a,b,l1,l2,bend=1):
 dx,dy=sub(b,a);d=math.hypot(dx,dy)
 assert abs(l1-l2)<d<l1+l2,(a,b,l1,l2,d)
 along=(l1*l1-l2*l2+d*d)/(2*d);h=math.sqrt(max(0,l1*l1-along*along))
 return (a[0]+dx/d*along+bend*dy/d*h,a[1]+dy/d*along-bend*dx/d*h)
CALVES={
 'near':((1150,60,1420,490),(1265,126),(1238,380),474),
 'far':((620,510,900,970),(724,569),(700,850),955),
}
foot_alpha=Image.open(BASE/'stride-v4/rig-source.png').getchannel('A')
FOOT_OUTLINES={side:[(x,y) for y in range(int(sa[1]),bounds[3],3) for x in range(bounds[0],bounds[2],3) if foot_alpha.getpixel((x,y))>128] for side,(bounds,sk,sa,sole) in CALVES.items()}
THIGHS={
 'near':((765,65,975,464),(840,123),(905,409)),
 'far':((180,520,405,945),(258,585),(330,877)),
}
def footpath(phase,shift,sole_offset):
 stance=.53
 if phase<stance:x=210+48-96*phase/stance;lift=0
 else:
  t=(phase-stance)/(1-stance);x=210-48+96*smooth(t);lift=23*math.sin(math.pi*t)
 x+=shift
 return (x,GROUND-SLOPE*x-sole_offset-lift)
def draw_leg(c,side,hip,ankle,foot_angle):
 knee=joint(hip,ankle,56,56)
 bounds,sk,sa,sole=CALVES[side];source_axis=sub(sa,sk);target_axis=sub(ankle,knee)
 scale=56/math.hypot(*source_axis)
 shin_angle=math.atan2(target_axis[1],target_axis[0])-math.atan2(source_axis[1],source_axis[0])
 shin=rigid(sa,ankle,shin_angle,scale);foot=rigid(sa,ankle,foot_angle,scale)
 def bend(p):
  weight=smooth((p[1]-(sa[1]-100))/100)
  a=shin(p);b=foot(p)
  return (a[0]*(1-weight)+b[0]*weight,a[1]*(1-weight)+b[1]*weight)
 bounds_t,a,b=THIGHS[side]
 draw_bone(c,rig,bounds_t,a,b,hip,knee)
 # One continuous calf/ankle/sandal mesh, never overlapping shin and shoe cutouts.
 fade=cairo.LinearGradient(0,sk[1]-40,0,sk[1]+70);fade.add_color_stop_rgba(0,1,1,1,0);fade.add_color_stop_rgba(1,1,1,1,1)
 draw_mesh(c,rig,bounds,bend,16,fade)
def surface_x(contour,y):
 hits=[]
 for a,b in zip(contour,contour[1:]+contour[:1]):
  if min(a[1],b[1])<=y<max(a[1],b[1]):
   t=(y-a[1])/(b[1]-a[1]);hits.append(a[0]+t*(b[0]-a[0]))
 assert hits,y
 return min(hits)
def draw_arm(c,shoulder,contact,hand_angle):
 # One upper arm plus one continuous forearm/hand, with no painted arm in torso.
 se=(1040,840);sw=(1250,430);sp=(1280,260)
 fore_length=53;scale=fore_length/math.dist(se,sw);hand_scale=scale*.70
 offset=rotate(sub(sp,sw),hand_angle);wrist=(contact[0]-offset[0]*hand_scale,contact[1]-offset[1]*hand_scale)
 elbow=joint(shoulder,wrist,55,fore_length,bend=-1)
 draw_bone(c,arms,(230,25,735,925),(405,180),(590,790),shoulder,elbow,True)
 source_axis=sub(sw,se);target_axis=sub(wrist,elbow)
 fore_angle=math.atan2(target_axis[1],target_axis[0])-math.atan2(source_axis[1],source_axis[0])
 fore=rigid(sw,wrist,fore_angle,scale);hand=rigid(sw,wrist,hand_angle,hand_scale)
 def bend(p):
  weight=smooth((530-p[1])/130)
  a=fore(p);b=hand(p)
  return (a[0]*(1-weight)+b[0]*weight,a[1]*(1-weight)+b[1]*weight)
 fade=cairo.LinearGradient(0,930,0,750);fade.add_color_stop_rgba(0,1,1,1,0);fade.add_color_stop_rgba(1,1,1,1,1)
 draw_mesh(c,arms,(900,20,1410,970),bend,20,fade)
def render(i,w=628):
 phase=(i*2/N)%1;turn=i*math.tau/N
 torso_angle=-.4+.025*math.sin(phase*math.tau*2)
 # Preserve the approved stance and head placement using a clean arm-/leg-free torso.
 body_scale=.15;hip=(267+2*math.sin(phase*math.tau*2),155-18*math.sin(phase*math.tau)**2)
 body=rigid((610,770),hip,torso_angle,body_scale)
 near_shoulder=body((910,430));far_shoulder=body((880,415))
 rotated=[rotate(p,turn) for p in polygon];cy=GROUND-SLOPE*450-max(y+SLOPE*x for x,y in rotated)
 contour=[(450+x,cy+y) for x,y in rotated]
 near_y=80+16*math.sin(i*math.tau/24);far_y=64+10*math.sin(i*math.tau/24+math.pi/2)
 contacts={'near':(surface_x(contour,near_y)+1,near_y),'far':(surface_x(contour,far_y)+1,far_y)}
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w,w//2);c=cairo.Context(surface);c.scale(w/628,w/628)
 c.save();c.transform(cairo.Matrix(1,.18-SLOPE,0,1,0,GROUND-310));c.move_to(0,310);c.line_to(628,197);c.line_to(628,314);c.line_to(0,314);c.close_path();c.clip();c.set_source_surface(ground,0,-11);c.paint();c.restore()
 c.save();c.translate(450,cy);c.rotate(turn);c.scale(rs,rs);c.set_source_surface(rock,-mx,-my);c.paint();c.restore()
 for side,offset in [('far',.5),('near',0)]:
  bounds,sk,sa,sole=CALVES[side];scale=56/math.dist(sk,sa);sole_offset=scale*(sole-sa[1])*math.sqrt(1+SLOPE*SLOPE)
  leg_phase=(phase+offset)%1
  h=(hip[0]-(4 if side=='far' else 0),hip[1])
  if leg_phase<.53:
   pitch=-math.atan(SLOPE)+.55*smooth((leg_phase/.53-.55)/.45)
  else:
   pitch=-math.atan(SLOPE)+.55*(1-smooth((leg_phase-.53)/.47))
  sole_points=FOOT_OUTLINES[side]
  support=max((rotate(sub(p,sa),pitch)[1]+SLOPE*rotate(sub(p,sa),pitch)[0])*scale for p in sole_points)
  ankle=footpath(leg_phase,hip[0]-220,support)
  c.push_group();draw_leg(c,side,h,ankle,pitch);layer=c.pop_group();c.set_source(layer);c.paint()
  if side=='far':c.set_source_rgba(.12,.10,.09,.18);c.mask(layer)
 c.push_group();draw_arm(c,far_shoulder,contacts['far'],.20);layer=c.pop_group();c.set_source(layer);c.paint();c.set_source_rgba(.12,.10,.09,.12);c.mask(layer)
 c.save();c.translate(*hip);c.rotate(torso_angle);c.scale(body_scale,body_scale);c.translate(-610,-770);c.set_source_surface(torso,0,0);c.paint();c.restore()
 draw_arm(c,near_shoulder,contacts['near'],.20)
 return surface
if __name__=='__main__':
 frames=OUT/'frames';frames.mkdir(exist_ok=True)
 for i in range(N):render(i,1256).write_to_png(str(frames/f'frame-{i:03}.png'))
 print('Rendered 96 review frames at 1256x628; live assets unchanged')
