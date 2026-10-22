import subprocess
from pathlib import Path
BASE=Path(__file__).resolve().parent
from PIL import Image,ImageDraw
raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(BASE/'codex-animated.mp4'),'-f','rawvideo','-pix_fmt','rgb24','-'])
w=368;size=w*w*3
sheet=Image.new('RGBA',(48,48*90))
for n in range(90):
 im=Image.frombytes('RGB',(w,w),raw[n*size:(n+1)*size])
 mask=Image.new('L',im.size); mask.putdata([255 if min(p)>215 and max(p)-min(p)<35 else 0 for p in im.getdata()])
 ImageDraw.floodfill(mask,(0,0),128,thresh=0)
 im=im.convert('RGBA');im.putalpha(mask.point(lambda p:0 if p==128 else 255))
 sheet.paste(im.resize((48,48),Image.Resampling.LANCZOS),(0,n*48))
sheet.save(BASE/'codex-working.png')
