#!/usr/bin/env python3
"""Render the original IconKing Lottie asset; requires rlottie-python and Pillow."""
from pathlib import Path
from PIL import Image
from rlottie_python import LottieAnimation
BASE=Path(__file__).resolve().parent
animation=LottieAnimation.from_file(str(BASE/'claude-animated.json'))
sheet=Image.new('RGBA',(48,48*85))
for i in range(85):
    sheet.paste(animation.render_pillow_frame(i*2,width=48,height=48),(0,i*48))
sheet.save(BASE/'claude-working.png')
