#!/usr/bin/env python3
"""Publish the approved motion-v3 animation without modifying the original mascot assets."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'assets/sisyphus-studies/anatomy-repair-v1/frames-v3'
if not (SOURCE/'frame-095.png').exists():
 import subprocess,sys
 subprocess.run([sys.executable,str(ROOT/'scripts/build-sisyphus-motion-v3.py')],check=True)
TARGET=ROOT/'assets/agent-mascots/painted-working'
TARGET.mkdir(parents=True,exist_ok=True)
css=['/* Approved painted Sisyphus motion-v3; original SVG theme remains available. */']
hashes={}
for i in range(96):
 name=f'frame-{i:03}.png';source=SOURCE/name
 shutil.copyfile(source,TARGET/name)
 hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
 css.append(f'#custom-agent_sisyphus.painted.working.f{i} {{ background-image: url("assets/agent-mascots/painted-working/{name}"); }}')
done=ROOT/'assets/agent-mascots/painted-complete.png'
shutil.copyfile(ROOT/'assets/sisyphus-studies/stride-v9/preview-done-v3.png',done)
# Three classes override the original complete.fN selector for every frame.
css.append('#custom-agent_sisyphus.painted.complete.done { background-image: url("assets/agent-mascots/painted-complete.png"); }')
(ROOT/'sisyphus-live.css').write_text('\n'.join(css)+'\n')
(TARGET/'manifest.json').write_text(json.dumps({'source':'anatomy-repair-v1/frames-v3','done_source':'stride-v9/preview-done-v3.png','done_sha256':hashlib.sha256(done.read_bytes()).hexdigest(),'fps':32,'frames':96,'sha256':hashes},indent=2)+'\n')
