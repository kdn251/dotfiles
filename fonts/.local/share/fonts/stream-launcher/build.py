from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path
from pathlib import Path
from xml.etree import ElementTree
names=['twitch','youtube','rumble']
fb=FontBuilder(1000,isTTF=True)
fb.setupGlyphOrder(['.notdef']+names)
fb.setupCharacterMap({0xE900+i:n for i,n in enumerate(names)})
glyphs={'.notdef':TTGlyphPen(None).glyph()}
for name in names:
 p=TTGlyphPen(None)
 pen=TransformPen(Cu2QuPen(p,1,reverse_direction=True),(32,0,0,-32,80,760))
 for node in ElementTree.parse(str(Path(__file__).parent / 'sources' / (name+'-logo.svg'))).iter():
  if node.tag.endswith('path'):parse_path(node.attrib['d'],pen)
 glyphs[name]=p.glyph()
fb.setupGlyf(glyphs)
fb.setupHorizontalMetrics({n:(960,80) for n in glyphs})
fb.setupHorizontalHeader(ascent=850,descent=-150)
fb.setupNameTable({'familyName':'Stream Launcher Icons','styleName':'Regular','uniqueFontIdentifier':'StreamLauncherIcons-1','fullName':'Stream Launcher Icons','psName':'StreamLauncherIcons','version':'Version 1.0'})
fb.setupOS2(sTypoAscender=850,sTypoDescender=-150,usWinAscent=850,usWinDescent=150)
fb.setupPost();fb.setupMaxp()
fb.save(str(Path(__file__).parent / 'StreamLauncherIcons.ttf'))
