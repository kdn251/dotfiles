# Upright posture comparison

The previous winner A is preserved in ../stride-v4/a (commit 9627cf6).
The original approved painting and earlier winners are also unchanged.
These are review studies only; the real agent-status mascot is unchanged.

All three variants retain the previous A's foot-path parameters: 130px stride,
23px lift, 53% stance, two complete alternating gait cycles per three-second
boulder revolution. They use the more upright, bent-elbow torso already present
in the preserved stride-v4/rig-source.png atlas, with three torso orientations:

- A: slight forward lean (0.08 radians).
- B: straighter back (0 radians).
- C: most upright (-0.08 radians).

Palms stay at the boulder. Hip attachment is computed from the torso transform;
the footpaths are translated along the incline to remain under the new hip
position. Leg lengths fit each posture, preventing the taller-looking torso
from leaving the legs in an exaggerated squat. Near and far feet remain exactly
half a cycle apart. The far-leg shadow and independently oriented sandals remain.
The painted artwork is reused directly; no new generated image is needed.

Rebuild with Python, Pillow and pycairo:

    python3 ~/.config/waybar/scripts/build-sisyphus-upright.py
    python3 ~/.config/waybar/scripts/sisyphus-studies.py build

The renderer's --large option produces 628x314 frames for comparison.gif export.
Rerun without --large afterward to restore 160x80 Waybar frames.
