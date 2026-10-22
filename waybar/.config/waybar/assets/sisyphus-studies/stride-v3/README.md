# Painted stride iteration

All three preview slots now use a new illustrated eight-pose pushing gait.
A: two complete gait cycles per three-second rock rotation (heavy).
B: three gait cycles (steady).
C: four gait cycles (quicker).

The figure lifts and advances its feet and knees. Each frame is registered to the
same hand position horizontally and inclined ground contact vertically. The same
painted boulder from rolling-v2 rotates independently. These are preview studies,
not replacements for the live status indicator or Telegram animation.

Approved original painted A remains untouched in ../painted/ (commit 44e8952).
Previous rolling B remains untouched in ../rolling-v2/ (commit 61a31af).

The generated sheet has some feet beyond its nominal grid boundaries, so
extract-sisyphus-stride.py extracts each connected figure instead of cutting feet
off with rectangular cells. It preserves the original sprite pixels and alpha.

Rebuild: extract-sisyphus-stride.py, then build-sisyphus-stride.py.
The latter renders 96 frames per variant at 160px for Waybar. --large renders
628px frames for preview export; rerun normally afterward for lightweight playback.
Dependencies: Python, Pillow and pycairo. Source illustrations are included.
