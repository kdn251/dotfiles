# Two independently moving arms

Based on the preferred stride-v7 C. The previous C remains unchanged at commit
5901b51. The front hand retains C's full mesh motion and boulder contour tracking.
The far arm is a separate painted layer with shoulder/elbow/hand articulation,
fixed upper/lower arm lengths, and its own moving boulder contact point. This
avoids scaling the entire arm as one piece or moving both hands as one silhouette.
The near torso overlays the far shoulder attachment. A subtle far-arm shade
helps distinguish the two arms when their silhouettes overlap.

Three versions vary the far-hand delay relative to C's front-hand motion:
- A: quarter-cycle offset.
- B: three-eighths-cycle offset.
- C: half-cycle offset (strongest alternating hand motion).

Front hand vertical travel remains 40px, rear hand travel is 20px at a separate
height. Both track the rolling boulder's contour. The two hands can naturally
pass behind one another briefly, but separate during each push cycle.

All three retain the winning uphill pose, 20/68 incline, original detailed atlas,
painted boulder, alternating feet, and 96-frame/32fps loop. Source art is reused
from stride-v4 and rolling-v2; no new artwork generation was required. Earlier
artwork and the actual live status mascot are unchanged.

Rebuild with Python, Pillow and pycairo:

    python3 ~/.config/waybar/scripts/build-sisyphus-two-hands.py
    python3 ~/.config/waybar/scripts/sisyphus-studies.py build

--large creates 628x314 preview frames for comparison.gif; rerun without it to
restore the 160x80 Waybar frames. The scripts and all source assets are preserved.
