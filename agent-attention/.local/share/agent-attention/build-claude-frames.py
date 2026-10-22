#!/usr/bin/env python3
"""Resample the existing Claude thinking GIF to a transparent 30fps strip."""
from pathlib import Path
from PIL import Image,ImageSequence
BASE=Path(__file__).resolve().parent
source=Image.open(BASE/'claude-thinking.gif')
frames=[];ends=[];total=0
for frame in ImageSequence.Iterator(source):
    frames.append(frame.convert('RGBA').copy())
    total+=frame.info.get('duration',100);ends.append(total)
count=round(total*30/1000)
sheet=Image.new('RGBA',(48,count*48))
for i in range(count):
    ms=i*total/count
    index=next(j for j,end in enumerate(ends) if ms<end)
    sheet.paste(frames[index].resize((48,48),Image.Resampling.LANCZOS),(0,i*48))
sheet.save(BASE/'claude-working.png')
