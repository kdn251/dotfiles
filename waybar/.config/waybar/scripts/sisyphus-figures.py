"""Detailed figure studies using the original Sisyphus boulder unchanged."""
import math,importlib.util,re,pathlib
spec=importlib.util.spec_from_file_location('original',pathlib.Path(__file__).with_name('build-agent-mascots.py'))
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)

def muscle(a,b,r1,r2,color,shade):
    dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy);nx=-dy/length;ny=dx/length
    def p(k,r):return (a[0]+dx*k+nx*r,a[1]+dy*k+ny*r)
    def q(v):return f'{v[0]:.3f} {v[1]:.3f}'
    # Tapered, curved muscles rather than rods or sharp polygon joints.
    outline=f'M{q(p(0,r1*.65))} Q{q(p(.28,r1*1.15))} {q(p(.7,r2*1.15))} Q{q(p(1.12,r2*.7))} {q(p(1,-r2*.65))} Q{q(p(.72,-r2))} {q(p(.2,-r1))} Q{q(p(-.12,-r1*.6))} {q(p(0,r1*.65))}Z'
    return f'<path d="{outline}" fill="{color}" stroke="{shade}" stroke-width=".28"/><path d="M{q(p(.12,-r1*.45))} Q{q(p(.4,-r1*.55))} {q(p(.77,-r2*.4))}" fill="none" stroke="#fff1cf" stroke-width=".38" opacity=".36" stroke-linecap="round"/>'

def frame(style,i,n=48):
    t=i*math.tau/n*2;bob=math.cos(t)*.28;breath=math.sin(t)*.3
    effort=math.sin(t);variant={'a':0,'b':1,'c':2}[style]
    source=original.sisyphus('working',i*24/n)
    defs=re.search(r'<defs>.*?</defs>',source,re.S).group()
    stone=re.search(r'<g transform="translate\(52 17\).*?</g>',source).group()
    angle=i*math.tau/n
    vertices=[(-13,-5),(-8,-12),(1,-14),(10,-9),(14,-1),(11,9),(3,13),(-7,11),(-13,4)]
    vertices=[(52+x*math.cos(angle)-y*math.sin(angle),17+x*math.sin(angle)+y*math.cos(angle)) for x,y in vertices]
    def left_edge(y):
        crossings=[]
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            if min(a[1],b[1])<=y<max(a[1],b[1]):crossings.append(a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
        return min(crossings)
    far_shift=left_edge(11.3+bob)-39
    near_shift=left_edge(16.4+bob)-39.1
    palette={'a':('#f2d3a4','#c18e67','#784d3d','#34272b','#bfc4b5','#737f76'),
             'b':('#f0cf9b','#b98660','#714736','#34272b','#b7bfac','#6e7a6c'),
             'c':('#efd5b1','#bd916e','#7a5541','#45332b','#c9c9b5','#7d8877')}[style]
    light,mid,dark,hair,cloth,fold=palette
    defs=defs[:-7]+f'''<linearGradient id="flesh" x1="0" y1="0" x2=".85" y2="1"><stop stop-color="{light}"/><stop offset=".52" stop-color="{mid}"/><stop offset="1" stop-color="{dark}"/></linearGradient><linearGradient id="linen" x1="0" y1="0" x2="1" y2=".8"><stop stop-color="{light if style=='c' else '#ede3c9'}"/><stop offset=".45" stop-color="{cloth}"/><stop offset="1" stop-color="{fold}"/></linearGradient></defs>'''
    parts=[defs,'<path d="M5 39 L73 19 L79 22 L79 27 L43 35 L34 40Z" fill="#37313e"/><path d="M5 39 L73 19 L77 20 L47 30 L30 33Z" fill="#8e7569"/><path d="M14 37 L30 32 L32 33 M47 28 L64 23" stroke="#c6a17b" stroke-width=".7"/>',stone]
    wide=1.02 if style=='a' else 1.1 if style=='b' else .97
    # Two distinct phases, with a planted forefoot and lifted recovery foot.
    for phase,hip,rear in ((t+math.pi,(25,26+bob),True),(t,(27,26+bob),False)):
        fx=20+math.sin(phase)*7; lift=max(0,math.cos(phase))*2.8
        fy=38-(fx-12)*.29-lift
        knee=((hip[0]+fx)/2+2.7,31.5-lift*.55)
        foot=(fx,fy)
        col=dark if rear else 'url(#flesh)'
        parts.append(muscle(hip,knee,2.1*wide,1.3,col,dark))
        parts.append(muscle(knee,foot,1.5*wide,.7,col,dark))
        parts.append(f'<path d="M{fx-.7:.2f} {fy-1:.2f} Q{fx+1.2:.2f} {fy+.2:.2f} {fx+.5:.2f} {fy+.7:.2f} L{fx-3:.2f} {fy+1:.2f} Q{fx-4:.2f} {fy+.3:.2f} {fx-2:.2f} {fy-.1:.2f}Z" fill="{col}"/>')
        if style in ('a','b','c'):parts.append(f'<path d="M{fx-2.8:.2f} {fy+.8:.2f} L{fx+.8:.2f} {fy+.4:.2f} M{fx-.4:.2f} {fy-.8:.2f} l-.5 1.5" fill="none" stroke="#52402e" stroke-width=".45"/>')
    parts.append(f'<g transform="translate(0 {bob})">')
    # Far arm sits behind the chest; its hand remains planted on the stone.
    elbow=(32.5+math.sin(t+.7)*(2.1+variant*.25),17.8+math.cos(t+.7)*1.5)
    parts.append(muscle((28,15.8),elbow,1.8,1.2,dark,dark))
    parts.append(muscle(elbow,(37.6+far_shift,11.3),1.3,.65,'url(#flesh)',dark))
    parts.append(f'<g transform="translate({far_shift} 0)"><path d="M36.8 11.7 L37.3 9.9 Q38.5 9.3 39.2 10 L39 12.2 L37.7 12.8Z" fill="{mid}"/></g>')
    # Broad shoulders, curved back, ribcage, waist, visible pectoral and scapula.
    parts.append(f'<path d="M27.6 13.5 Q30.6 13.1 31.6 16.1 Q30.9 18.7 29.5 21.3 L28.9 25.4 Q26 26.2 23 24.7 L23.7 20.8 L24.9 16.7 Q25.6 14.6 27.6 13.5Z" fill="url(#flesh)" stroke="{dark}" stroke-width=".4"/>')
    parts.append(f'<path d="M25.6 16.1 Q26.7 14.7 28.9 15.1 Q27.4 17.4 26.2 20.3 L24.4 23.2 L25 19Z" fill="{light}" opacity=".34"/><path d="M28.2 17.5 Q30 18.2 29.3 20 M26 20.3 Q25.7 22 26.8 23 M27.1 22.4 L29 22.9" fill="none" stroke="{dark}" stroke-width=".38" opacity=".48"/>')
    # Linen wrapped around the pelvis with layered folds and an asymmetric hem.
    parts.append(f'<path d="M21 23.5 Q25 25.8 29.5 23.7 L31.1 27.9 L28.1 30.2 L24.9 28.6 L21 29.3 L20.2 26.3Z" fill="url(#linen)" stroke="{fold}" stroke-width=".4"/><path d="M22 25 L24.2 28.3 M25.4 25.6 L26.9 28.9 M28.5 25 L29.1 28.3" fill="none" stroke="{fold}" stroke-width=".5" opacity=".7"/><path d="M21 23.7 Q25.6 25.7 29.3 24" fill="none" stroke="{light}" stroke-width=".7"/>')
    # Neck and a real profile: brow, nose, cheek, jaw, hair and beard.
    parts.append(f'<path d="M27.5 13.7 L27.5 10.9 L31 10.5 L31.4 14.7 Q29.3 16 27.5 13.7Z" fill="url(#flesh)"/>')
    parts.append(f'<path d="M26.7 7 Q29 4.9 32 6.6 L33 8.5 L34 10 L32.8 10.5 L32.6 12.4 L30.6 13.5 L27.4 11.9 L26.2 9.6Z" fill="url(#flesh)" stroke="{dark}" stroke-width=".24"/>')
    parts.append(f'<path d="M26.6 10.2 Q24.8 8.8 25.9 6.8 Q26.1 5.3 27.6 5.4 Q28.3 3.9 29.6 4.7 Q31.2 4.2 32.6 5.5 L33.1 7.4 Q30.8 6.5 29.8 7.6 L28.2 7.2 L27.5 10.5Z" fill="{hair}"/>')
    parts.append(f'<path d="M27.8 6 Q29.2 5.5 30.3 5.9 M26.4 7.1 L27.8 6.8" stroke="{mid if style!='c' else light}" stroke-width=".35" opacity=".55" fill="none"/>')
    if True:
        parts.append(f'<path d="M28 10.2 L29.8 11.5 L32.7 10.8 L32.9 13.4 L30.2 15.4 L27.9 13.7 L27 11.2Z" fill="{hair}"/><path d="M29 12 L29.7 14 M30.7 12.1 L30.6 14.4" stroke="{mid}" stroke-width=".32" opacity=".5"/>')
    else:parts.append(f'<path d="M28.2 11.6 Q30.7 13.2 32.7 11.2 L32.2 13 L30.2 13.8Z" fill="{hair}" opacity=".65"/>')
    parts.append(f'<path d="M31 8.6 L32.1 8.8" stroke="{hair}" stroke-width=".45" stroke-linecap="round"/><ellipse cx="27.9" cy="9.6" rx=".55" ry=".8" fill="{mid}"/>')
    # Near arm has a rounded deltoid and flexed biceps, not a stick outline.
    elbow=(32+effort*(2.6+variant*.35),20.4+math.cos(t)*(1.9+variant*.2))
    parts.append(muscle((28,16.5),elbow,1.9*wide,1.45,'url(#flesh)',dark))
    parts.append(muscle(elbow,(38+near_shift,16.4),1.65,.72,'url(#flesh)',dark))
    parts.append(f'<g transform="translate({near_shift} 0)"><path d="M37 16.6 L37.8 14.8 Q39 14.2 39.7 14.8 L39.1 17 L37.9 17.5Z" fill="{light}" stroke="{dark}" stroke-width=".25"/><path d="M38.4 15 L38.1 16.5" stroke="{dark}" stroke-width=".22"/></g>')
    parts.append(f'<path d="M26.5 15.6 Q27.5 14.8 28.8 15.2 M25.5 18.3 L25 20.7 M27.1 6.3 Q28.4 5.5 29.4 6.2 M29.7 5.6 L31.4 6.3 M28.9 12.3 L29.5 13.8 M30.4 12.4 L30.4 14.2" stroke="{light}" stroke-width=".25" fill="none" opacity=".45"/>')
    if style=='b':
        parts.append(f'<path d="M25.2 15 L26.5 14.1 L29.8 24 L28.3 24.5Z" fill="url(#linen)" opacity=".9"/>')
    if style=='c':
        parts.append(f'<path d="M21.6 25.2 Q20.5 28.2 {18.6+effort*.65} 29.8 L22.2 29.2 L24 26.1Z" fill="url(#linen)"/>')
    parts.append('</g>')
    return '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40" viewBox="0 0 80 40">'+''.join(parts)+'</svg>'
