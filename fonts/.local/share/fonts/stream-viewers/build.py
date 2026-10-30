from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import RecordingPen, replayRecording
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.svgLib.path import parse_path
from pathlib import Path
from xml.etree import ElementTree
names=['viewer']
fb=FontBuilder(1000,isTTF=True)
fb.setupGlyphOrder(['.notdef']+names)
fb.setupCharacterMap({0x100001+i:n for i,n in enumerate(names)})
glyphs={'.notdef':TTGlyphPen(None).glyph()}
for name in names:
 p=TTGlyphPen(None)
 recording=RecordingPen()
 pen=TransformPen(Cu2QuPen(recording,1,reverse_direction=True),(38.4,0,0,-38.4,3.2,852))
 for node in ElementTree.parse(str(Path(__file__).parent / (name+'.svg'))).iter():
  if node.tag.endswith('path'):parse_path(node.attrib['d'],pen)
 # The SVG uses even-odd fill: its second contour is the hollow head.
 # TrueType uses winding direction instead, so reverse that inner contour.
 contours=[]
 for operation in recording.value:
  if operation[0]=='moveTo':contours.append([])
  contours[-1].append(operation)
 if len(contours)!=2:raise ValueError('Expected outer silhouette and head cutout')
 for index, contour in enumerate(contours):
  replayRecording(contour, ReverseContourPen(p) if index==1 else p)
 glyphs[name]=p.glyph()
fb.setupGlyf(glyphs)
fb.setupHorizontalMetrics({n:(960,80) for n in glyphs})
fb.setupHorizontalHeader(ascent=850,descent=-150)
fb.setupNameTable({'familyName':'Stream Viewer Icons','styleName':'Regular','uniqueFontIdentifier':'StreamViewerIcons-4','fullName':'Stream Viewer Icons','psName':'StreamViewerIcons','version':'Version 1.3'})
fb.setupOS2(sTypoAscender=850,sTypoDescender=-150,usWinAscent=850,usWinDescent=150)
fb.setupPost();fb.setupMaxp()
fb.save(str(Path(__file__).parent / 'StreamViewerIcons.ttf'))
