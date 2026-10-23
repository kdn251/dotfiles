# Approved Sisyphus motion v3

96 painted working frames at 32fps, with repaired anatomy, constrained ankle
rotation, flexing wrists and flowing hair. Completion uses the matching seated
pose and green check in ../painted-complete.png. The manifest records sources
and hashes. Idle and unavailable monitors freeze the working image; attention
retains its existing artwork. Local and remote lifecycle monitoring is unchanged.

## Rebuild

    python3 ~/.config/waybar/scripts/build-sisyphus-motion-v3.py
    python3 ~/.config/waybar/scripts/build-sisyphus-live.py

Requires Python, Pillow and pycairo. Installed frames are included, so normal
Waybar startup does not require generation. Source art, prompts, preview GIFs,
and renderer are retained under sisyphus-studies and scripts.

## Previous versions

Original painted A is preserved in sisyphus-studies/stride-v9/a and preview.gif.
Anatomy v2 and motion v3 comparison previews remain alongside it. Original SVG
assets and generator remain unchanged. Append --classic to agent-status.py in
config.jsonc to restore the original SVG theme, then restart waybar.service.
