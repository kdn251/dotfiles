#!/usr/bin/env python3
"""Three independent artwork studies. Preview only, never agent activity."""
import json,math,pathlib,sys,time
ROOT=pathlib.Path(__file__).resolve().parent.parent
ASSETS=ROOT/'assets/sisyphus-studies'
N=96
NAMES={'a':'Painted stride · slow and heavy','b':'Painted stride · steady','c':'Painted stride · quicker drive'}

import importlib.util
_spec=importlib.util.spec_from_file_location('figures',pathlib.Path(__file__).with_name('sisyphus-figures.py'))
_figures=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_figures)
def frame(style,i):return _figures.frame(style,i,N)

def build():
    ASSETS.mkdir(parents=True,exist_ok=True)
    css=['/* Generated Sisyphus artwork studies, not live status. */']
    for style in NAMES:
        for i in range(N):
            (ASSETS/f'{style}-{i}.svg').write_text(frame(style,i))
            asset=f'stride-v3/{style}/frame-{i:03}.png'
            css.append(f'#custom-sisyphus_study_{style}.f{i} {{ background-image:url("assets/sisyphus-studies/{asset}"); }}')
    (ROOT/'sisyphus-studies.css').write_text('\n'.join(css)+'\n')

if __name__=='__main__':
    if sys.argv[1]=='build':build()
    else:
        style=sys.argv[1]
        try:
            while True:
                print(json.dumps({'text':style.upper(),'class':['f'+str(int(time.monotonic()*32)%N)],'tooltip':NAMES[style]+' · animation study (not live status)'}),flush=True)
                time.sleep(1/32)
        except (BrokenPipeError,KeyboardInterrupt):pass
