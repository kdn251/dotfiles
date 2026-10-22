#!/usr/bin/env python3
"""Publish the approved A animation without modifying the original mascot assets."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'assets/sisyphus-studies/stride-v9/a'
TARGET=ROOT/'assets/agent-mascots/painted-working'
TARGET.mkdir(parents=True,exist_ok=True)
css=['/* Approved painted Sisyphus A; original SVG theme remains available. */']
hashes={}
for i in range(96):
 name=f'frame-{i:03}.png';source=SOURCE/name
 shutil.copyfile(source,TARGET/name)
 hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
 css.append(f'#custom-agent_sisyphus.painted.working.f{i} {{ background-image: url("assets/agent-mascots/painted-working/{name}"); }}')
(ROOT/'sisyphus-live.css').write_text('\n'.join(css)+'\n')
(TARGET/'manifest.json').write_text(json.dumps({'source':'stride-v9/a','fps':32,'frames':96,'sha256':hashes},indent=2)+'\n')
