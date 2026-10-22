#!/usr/bin/env python3
"""Paint shaded vector sprites for high-DPI Waybar."""
import math
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
ASSETS=ROOT/'assets/agent-mascots'
FRAMES=24

def svg(body):
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40" viewBox="0 0 80 40"><defs>
<linearGradient id="fire" x1="0%" y1="100%" x2="20%" y2="0%"><stop stop-color="#ffe595"/><stop offset=".42" stop-color="#ffb638"/><stop offset=".75" stop-color="#ff6026"/><stop offset="1" stop-color="#ca2926"/></linearGradient>
<linearGradient id="stone" x2="100%" y2="100%"><stop stop-color="#bdc4ce"/><stop offset=".4" stop-color="#727c91"/><stop offset="1" stop-color="#33394e"/></linearGradient>
<linearGradient id="skin" x2="100%" y2="100%"><stop stop-color="#ffe0a1"/><stop offset=".5" stop-color="#d7995f"/><stop offset="1" stop-color="#925548"/></linearGradient>
<radialGradient id="glow"><stop stop-color="#ff8c27" stop-opacity=".24"/><stop offset="1" stop-color="#ff5a1d" stop-opacity="0"/></radialGradient>
</defs>'''+body+'</svg>\n'

def calcifer(state,frame):
    t=frame*math.tau/FRAMES; w=math.sin(t); v=math.sin(t*2+.8)
    body='<ellipse cx="40" cy="24" rx="25" ry="17" fill="url(#glow)"/>'
    body+='<path d="M24 34 L52 38 L56 35 L28 31Z" fill="#402b32" stroke="#241f29"/><path d="M25 34 L52 37 L54 35 L27 32Z" fill="#8e4b36"/><path d="M26 37 L55 31 L57 34 L28 40Z" fill="#482c30"/><path d="M28 37 L55 32" stroke="#c77b41" stroke-width="1.4"/><path d="M34 36 L39 35 M44 34 L49 33" stroke="#ffd071" stroke-width="1.3"/>'
    body+=f'<path d="M27 33 C20 28 22 22 25 17 Q27 12 24 {9+w} Q31 12 32 18 C36 12 32 7 37 {2+v} Q35 9 42 12 Q45 8 44 {4-w} C53 12 46 15 51 19 Q55 17 54 13 C63 24 56 32 50 34 Q38 39 27 33Z" fill="#962b29" stroke="#291e28" stroke-width="1.3"/>'
    body+=f'<path d="M28 33 C22 29 24 23 28 17 L29 23 Q36 16 35 {10+w} Q40 11 41 19 Q46 16 47 {11-v} Q52 19 49 23 L54 20 Q59 30 49 34 Q39 37 28 33Z" fill="url(#fire)"/>'
    body+='<path d="M29 32 Q25 27 30 24 Q29 28 34 28 Q36 20 39 20 Q37 25 42 27 Q46 22 48 25 Q53 32 46 35 Q36 37 29 32Z" fill="#ffe5a0"/>'
    ey=23 if state=='working' else 21.8
    blink=.8 if frame in (17,18) and state=='working' else 3.3
    for x in (33,45):
        body+=f'<ellipse cx="{x}" cy="{ey}" rx="3.6" ry="{blink}" fill="#fff9df" stroke="#ba632e" stroke-width=".5"/><ellipse cx="{x+.5}" cy="{ey+.4}" rx="1.05" ry="{min(blink,2)}" fill="#302126"/>'
    if state=='working':
        body+='<path d="M35 29 Q39 32 43 28 Q40 35 35 29Z" fill="#6e2926"/><path d="M37 31 L41 30" stroke="#f88b59" stroke-width=".8"/>'
    else:
        body+='<ellipse cx="39" cy="30" rx="2.4" ry="3" fill="#662326"/><path d="M27 26 Q19 25 18 19 M52 26 Q60 23 60 17" stroke="#ffaf3e" stroke-width="2.2" fill="none" stroke-linecap="round"/>'
        body+=f'<path d="M65 {7+w} v8" stroke="#ffe5a0" stroke-width="2.5" stroke-linecap="round"/><circle cx="65" cy="20" r="1.5" fill="#ffe5a0"/>'
    for j in range(3):
        phase=(frame/FRAMES+j/3)%1; x=22+j*17+math.sin(t+j)*2; y=23-phase*20
        body+=f'<path d="M{x:.1f} {y:.1f} l1 -2 l.5 2 l-1 1Z" fill="#ffc763" opacity="{1-phase:.2f}"/>'
    return svg(body)

def sisyphus(state,frame):
    t=frame*math.tau/FRAMES; w=math.sin(t); stride=math.sin(t*2)
    body='<path d="M5 39 L73 19 L79 22 L79 27 L43 35 L34 40Z" fill="#37313e"/><path d="M5 39 L73 19 L77 20 L47 30 L30 33Z" fill="#8e7569"/><path d="M14 37 L30 32 L32 33 M47 28 L64 23" stroke="#c6a17b" stroke-width="1"/>'
    rotation=frame*360/FRAMES if state=='working' else 0
    body+=f'<g transform="translate(52 17) rotate({rotation})"><path d="M-13 -5 L-8 -12 L1 -14 L10 -9 L14 -1 L11 9 L3 13 L-7 11 L-13 4Z" fill="url(#stone)" stroke="#22242e" stroke-width="1.2"/><path d="M-12 -5 L-7 -11 L1 -13 L8 -8 L-1 -6 L-7 1Z" fill="#c1c6c9"/><path d="M-7 1 L-1 -6 L8 -8 L12 -1 L6 3 L-3 5Z" fill="#8e99a8"/><path d="M-3 5 L6 3 L10 9 L3 12 L-6 10Z" fill="#566176"/><path d="M-7 -10 L-3 -7 L-4 -2 L0 1 M8 -6 L5 -1 L6 3 L3 7 M-9 6 L-5 5" stroke="#4d5569" stroke-width="1" fill="none"/><path d="M-11 -5 L-7 -10 L0 -12" stroke="#e4ddc4" stroke-width="1" fill="none"/></g>'
    bob=math.cos(t*2)*.8 if state=='working' else 0
    body+=f'<g transform="translate(0 {bob})" stroke-linejoin="round">'
    if state=='working':
        # Opposing strides with lifted recovery feet; planted feet follow the slope.
        for phase,hip,color in ((t,24,'#ab7155'),(t+math.pi,28,'url(#skin)')):
            foot=21+math.sin(phase)*7
            lift=max(0,math.cos(phase))*3
            fy=38-(foot-12)*.29-lift
            knee=(hip+foot)/2+3
            ky=29-lift*.6
            body+=f'<path d="M{hip} 26 Q{knee} {ky-1} {knee} {ky+1} L{foot} {fy} l-3 .5" stroke="#392a32" stroke-width="4.8" fill="none" stroke-linecap="round"/><path d="M{hip} 26 Q{knee} {ky-1} {knee} {ky+1} L{foot} {fy} l-3 .5" stroke="{color}" stroke-width="3.5" fill="none" stroke-linecap="round"/>'

        body+=f'<path d="M25 14 Q20 16 20 21 L24 27 L31 26 L31 21 L29 17Z" fill="url(#skin)" stroke="#392a32" stroke-width=".8"/><path d="M23 16 Q26 15 28 18 L{31-w*2.5} {20+w*1.5} L37 15 L39 15 L38 18 L{31-w*2.5} {23+w*1.5} L27 21Z" fill="url(#skin)" stroke="#583a37" stroke-width=".7"/><path d="M26 16 L{31+w*2} {16+w} L36 11 L39 10 L39 12 L{33+w*2} {19+w} L28 19" fill="#eac18a" stroke="#583a37" stroke-width=".6"/><path d="M21 21 L27 23 L31 23 L33 28 L25 29 L21 26Z" fill="#bac6c2" stroke="#37404a" stroke-width=".7"/><path d="M24 24 L26 28 L30 27 L28 23Z" fill="#e8e3c7"/>'
        body+='<path d="M26 9 Q31 8 32 12 L30 16 L26 15 L24 12Z" fill="url(#skin)"/><path d="M24 10 L26 7 L30 7 L32 10 L28 10 L26 12 L25 14 L23 12Z" fill="#4a3033"/><path d="M29 14 L32 12 L31 16 L28 17Z" fill="#63413c"/>'
    else:
        body+='<path d="M23 27 L21 34 L16 37 L12 37 L18 33 L19 26 M28 27 L30 34 L26 36 L23 36 L26 32 L24 28" fill="url(#skin)" stroke="#392a32" stroke-width=".8"/><path d="M23 13 Q18 15 19 20 L21 27 L29 26 L28 18 L26 14Z" fill="url(#skin)" stroke="#392a32" stroke-width=".8"/><path d="M26 15 L31 18 L38 14 L39 16 L32 22 L27 20 M20 16 L15 15 L13 8 L10 7 L11 17 L19 21" fill="url(#skin)" stroke="#583a37" stroke-width=".7"/><path d="M20 23 L28 22 L31 28 L21 29Z" fill="#c3cfca" stroke="#37404a" stroke-width=".8"/><path d="M24 24 L25 28 L29 27" fill="#f0e4c6"/><path d="M21 6 Q26 4 28 8 L27 12 L24 14 L21 11Z" fill="url(#skin)"/><path d="M21 8 L19 7 L21 4 L26 4 L29 7 L25 6 L23 8Z M23 12 L27 10 L27 14 L24 15Z" fill="#4a3033"/>'
        if state=='complete':body+='<path d="M3 10 L7 14 L14 5" fill="none" stroke="#b3f0a8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        else:body+=f'<path d="M6 {3+w} v7" stroke="#ffe3a1" stroke-width="2" stroke-linecap="round"/><circle cx="6" cy="14" r="1.3" fill="#ffe3a1"/>'
    body+='</g>'
    if state=='working':body+=f'<path d="M{10+w} 35 l-3 1 M{16-w} 38 l-3 1" stroke="#9a8372" stroke-width="1" opacity=".65"/>'
    return svg(body)

def main():
    ASSETS.mkdir(parents=True,exist_ok=True)
    css=['/* Generated by scripts/build-agent-mascots.py. */']
    for name,draw in [('calcifer',calcifer),('sisyphus',sisyphus)]:
        for state in (('working','attention','complete') if name=='sisyphus' else ('working','attention')):
            for frame in range(FRAMES):
                filename=f'{name}-{state}-{frame}.svg'
                (ASSETS/filename).write_text(draw(state,frame))
                css.append(f'#custom-agent_{name}.{state}.f{frame} {{ background-image: url("assets/agent-mascots/{filename}"); }}')
    (ROOT/'agent-mascots.css').write_text('\n'.join(css)+'\n')
if __name__=='__main__':main()
