#!/usr/bin/env python3
"""Extract the eight generated sprites without clipping feet at grid boundaries."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter,ImageChops
BASE=Path(__file__).resolve().parent.parent/'assets/sisyphus-studies/stride-v3'
im=Image.open(BASE/'character-sheet.png').convert('RGBA');w,h=im.size
base=im.getchannel('A').point(lambda x:255 if x>150 else 0)
for i in range(8):
    mask=base.copy();seed=(int(w*(.29+(i%2)*.5)),int(h*(.115+(i//2)*.25)))
    assert mask.getpixel(seed)==255,seed
    ImageDraw.floodfill(mask,seed,128)
    mask=mask.point(lambda x:255 if x==128 else 0).filter(ImageFilter.MaxFilter(5))
    frame=im.copy();frame.putalpha(ImageChops.multiply(im.getchannel('A'),mask))
    frame.save(BASE/f'person-{i}.png')
