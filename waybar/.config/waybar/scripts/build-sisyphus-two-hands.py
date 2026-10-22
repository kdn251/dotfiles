#!/usr/bin/env python3
"""Independent two-arm pushing studies based on the winning C hand motion."""
from pathlib import Path
import math,sys,json,cairo
from PIL import Image
BASE=Path(__file__).resolve().parent.parent/'assets/sisyphus-studies'
OUT=BASE/'stride-v8';N=96
SLOPE=20/68;GROUND=345
rig=cairo.ImageSurface.create_from_png(str(BASE/'stride-v4/rig-source.png'))
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
VARIANTS={'a':.5,'b':.75,'c':1.0}
def foot_at(p,stride,lift,stance):
 if p<stance:
  t=p/stance;x=210+stride-2*stride*t;h=0
 else:
  t=(p-stance)/(1-stance);s=t*t*(3-2*t);x=210-stride+2*stride*s;h=lift*math.sin(math.pi*t)
 return (x,GROUND-SLOPE*x-18-h)
# A native textured animation mesh preserves the painted body while articulating
# elbows, wrists and hands. Shoulder, head, pelvis and cloth remain anchored.
TORSO_CACHE={}
def smooth(t):
 t=max(0,min(1,t));return t*t*(3-2*t)
def animated_torso(style,i,angle):
 key=(style,i%N)
 if key in TORSO_CACHE:return TORSO_CACHE[key]
 hx,hy,ex,ey=5,20,7,8;wave=math.sin(i*math.tau/24)
 # Convert world-space joint movement to the atlas coordinate system.
 def local(x,y):return ((x*math.cos(angle)+y*math.sin(angle))/.36,(-x*math.sin(angle)+y*math.cos(angle))/.36)
 # Find the rolling rock's left contour at the palm height, so the hands
 # follow the stone rather than drifting in empty space.
 rotation=i*math.tau/N
 polygon=outline[::2]+list(reversed(outline[1::2]))
 rotated=[(x*math.cos(rotation)-y*math.sin(rotation),x*math.sin(rotation)+y*math.cos(rotation)) for x,y in polygon]
 cy=GROUND-SLOPE*450-max(y+SLOPE*x for x,y in rotated)
 contact_y=80+hy*wave
 crossings=[]
 for a,b in zip(rotated,rotated[1:]+rotated[:1]):
  if min(a[1],b[1])<=contact_y-cy<max(a[1],b[1]):
   t=(contact_y-cy-a[1])/(b[1]-a[1]);crossings.append(450+a[0]+t*(b[0]-a[0]))
 assert crossings, (style,i,contact_y)
 contact_x=min(crossings)-4+hx*wave*.1
 hand=local(contact_x-360,hy*wave);elbow=local(-ex*wave,ey*wave)
 def warp(x,y):
  hand_weight=smooth((x-1385)/40)*smooth((850-y)/70)
  elbow_weight=math.exp(-((x-1325)/80)**2-((y-790)/55)**2)*(1-hand_weight)
  return (x+hand[0]*hand_weight+elbow[0]*elbow_weight,y+hand[1]*hand_weight+elbow[1]*elbow_weight)
 out=cairo.ImageSurface(cairo.FORMAT_ARGB32,636,564);ctx=cairo.Context(out);ctx.translate(-940,-500)
 xs=list(range(940,1536,20))+[1536];ys=list(range(500,1024,20))+[1024]
 for y0,y1 in zip(ys,ys[1:]):
  for x0,x1 in zip(xs,xs[1:]):
   for src in (((x0,y0),(x1,y0),(x1,y1)),((x0,y0),(x1,y1),(x0,y1))):
    dst=[warp(*p) for p in src]
    a,b,d=src;u,v,z=dst
    source=cairo.Matrix(b[0]-a[0],b[1]-a[1],d[0]-a[0],d[1]-a[1],a[0],a[1]);source.invert()
    target=cairo.Matrix(v[0]-u[0],v[1]-u[1],z[0]-u[0],z[1]-u[1],u[0],u[1])
    # Cairo Matrix multiplication applies the left matrix first.
    transform=source.multiply(target)
    ctx.save();ctx.set_antialias(cairo.ANTIALIAS_NONE)
    ctx.move_to(*u);ctx.line_to(*v);ctx.line_to(*z);ctx.close_path();ctx.clip()
    ctx.transform(transform);ctx.set_source_surface(rig,0,0);ctx.paint();ctx.restore()
 TORSO_CACHE[key]=out
 return out
def render(style,i,w):
 posture,body_scale,palm_x,palm_y=-.4,.36,360,80;stride,lift,stance=48,23,.53;phase=(i*2/N)%1
 leg_length=(63,65)
 torso_angle=posture+.025*math.sin(phase*math.tau*2)
 hx,hy=-348*body_scale,160*body_scale
 hip=(palm_x+hx*math.cos(torso_angle)-hy*math.sin(torso_angle),palm_y+hx*math.sin(torso_angle)+hy*math.cos(torso_angle))
 shift=hip[0]-245
 feet={side:foot_at((phase+offset)%1,stride,lift,stance) for side,offset in [('near',0),('far',.5)]}
 feet={side:(x+shift,y-SLOPE*shift) for side,(x,y) in feet.items()}
 surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,w,w//2);c=cairo.Context(surface);c.scale(w/628,w/628)
 c.save();c.transform(cairo.Matrix(1,.18-SLOPE,0,1,0,GROUND-310));c.move_to(0,310);c.line_to(628,197);c.line_to(628,314);c.line_to(0,314);c.close_path();c.clip();c.set_source_surface(ground,0,-11);c.paint();c.restore()
 angle=i*math.tau/N;rot=[(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle)) for x,y in outline]
 cx=450;cy=GROUND-SLOPE*cx-max(y+SLOPE*x for x,y in rot)
 c.save();c.translate(cx,cy);c.rotate(angle);c.scale(rs,rs);c.set_source_surface(rock,-mx,-my);c.paint();c.restore()
 for side in ('far','near'):
  c.push_group()
  foot=feet[side];h=(hip[0]-(4 if side=='far' else 0),hip[1]);knee=solve(h,foot,*leg_length)
  bone(c,side+'_shin',knee,foot)
  bone(c,side+'_thigh',h,knee)
  # Sandals stay parallel to the slope, independent of shin rotation.
  c.save();c.translate(*foot);c.rotate(-math.atan(SLOPE));c.scale(.235,.235);a=PARTS[side+'_foot'][1];c.translate(-a[0],-a[1]);cut(c,PARTS[side+'_foot'][0]);c.restore()
  layer=c.pop_group();c.set_source(layer);c.paint()
  if side=='far':
   c.set_source_rgba(.12,.10,.09,.24);c.mask(layer)
 # Keep A's torso and gait, then articulate its painted elbow/wrist/hand mesh.
 # The far arm is its own painted layer, anchored at the shoulder and reaching
 # a separate moving contact point on the rock. The near arm remains C's mesh.
 sx,sy=1230,715;px,py=1455,680
 shoulder=(palm_x+.36*((sx-1448)*math.cos(torso_angle)-(sy-720)*math.sin(torso_angle)),palm_y+.36*((sx-1448)*math.sin(torso_angle)+(sy-720)*math.cos(torso_angle)))
 phase_delay=VARIANTS[style]*math.pi
 far_y=64+10*math.sin(i*math.tau/24+phase_delay)
 poly=outline[::2]+list(reversed(outline[1::2]))
 contour=[(450+x*math.cos(angle)-y*math.sin(angle),cy+x*math.sin(angle)+y*math.cos(angle)) for x,y in poly]
 hits=[]
 for a,b in zip(contour,contour[1:]+contour[:1]):
  if min(a[1],b[1])<=far_y<max(a[1],b[1]):
   t=(far_y-a[1])/(b[1]-a[1]);hits.append(a[0]+t*(b[0]-a[0]))
 assert hits,(style,i,far_y)
 far_hand=(min(hits)-3,far_y)
 dx,dy=far_hand[0]-shoulder[0],far_hand[1]-shoulder[1];distance=math.hypot(dx,dy)
 l1,l2=49,65
 assert distance<l1+l2,(style,i,distance)
 along=(l1*l1-l2*l2+distance*distance)/(2*distance);side=math.sqrt(max(0,l1*l1-along*along))
 elbow=(shoulder[0]+dx/distance*along-dy/distance*side,shoulder[1]+dy/distance*along+dx/distance*side)
 def arm_piece(points,source_a,source_b,target_a,target_b):
  ux,uy=source_b[0]-source_a[0],source_b[1]-source_a[1];vx,vy=target_b[0]-target_a[0],target_b[1]-target_a[1]
  scale=math.hypot(vx,vy)/math.hypot(ux,uy)
  c.save();c.translate(*target_a);c.rotate(math.atan2(vy,vx)-math.atan2(uy,ux));c.scale(scale,scale);c.translate(-source_a[0],-source_a[1])
  c.move_to(*points[0])
  for point in points[1:]:c.line_to(*point)
  c.close_path();c.clip();c.set_source_surface(rig,0,0);c.paint();c.restore()
 c.push_group()
 arm_piece([(1170,690),(1210,660),(1260,680),(1335,745),(1360,780),(1340,830),(1300,835),(1245,790),(1190,745)],(1230,715),(1325,790),shoulder,elbow)
 arm_piece([(1300,765),(1340,740),(1398,715),(1420,665),(1450,640),(1475,645),(1485,680),(1465,735),(1445,775),(1365,823),(1315,840)],(1325,790),(1455,680),elbow,far_hand)
 far_arm=c.pop_group();c.set_source(far_arm);c.paint();c.set_source_rgba(.12,.10,.09,.12);c.mask(far_arm)
 c.save();c.translate(palm_x,palm_y);c.rotate(torso_angle);c.scale(body_scale,body_scale);c.translate(-1448,-720)
 c.set_source_surface(animated_torso(style,i,torso_angle),940,500);c.paint();c.restore()
 return surface,feet
if __name__=='__main__':
 width=628 if '--large' in sys.argv else 160
 checks=[]
 for style in VARIANTS:
  target=OUT/style;target.mkdir(parents=True,exist_ok=True)
  for i in range(N):
   s,feet=render(style,i,width);s.write_to_png(str(target/f'frame-{i:03}.png'))
   if i%6==0:checks.append({'variant':style,'frame':i,'near':feet['near'],'far':feet['far']})
 (OUT/'foot-positions.json').write_text(json.dumps(checks,indent=2)+'\n')
 print('Rendered three alternating gait variants:',width,'px,',N,'frames each')
