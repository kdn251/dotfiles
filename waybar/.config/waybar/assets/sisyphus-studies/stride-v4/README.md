# Alternating painted gait studies

The round-three winner A remains unchanged in ../stride-v3/a at commit 1b3abd5.
The original approved painting remains unchanged in ../painted at 44e8952.
These are three review previews only; the live activity mascot is unchanged.

All three retain the winner's slow cadence: two complete left/right gait cycles
per three-second boulder rotation, 96 frames at 32 fps. The original painted
boulder and ground come from ../rolling-v2 and remain unchanged.

- A: moderate 130px stride, 23px foot clearance.
- B: wider 144px stride, 30px clearance.
- C: compact 120px stride, 34px clearance for a more visible climbing step.

Unlike the previous generated pose sequence, the legs now have independent
ankle paths offset by exactly half a cycle. A two-bone solve positions each knee.
Each leg stays in its correct foreground/background layer throughout the cycle.
The far leg has a subtle shadow to make the alternating lead leg easier to read.
Sandals remain parallel to the incline, independent of shin rotation. The upper
body pivots slightly around its palms as the knees bend under the load.

The generated atlas is included as rig-source.png. The renderer clips its parts
non-destructively and composites them using documented anatomical pivot points.
Three unsuccessful generated whole-pose sheets were discarded because they
still kept the same lead leg forward; they are not used in these previews.

Rebuild with Python, Pillow, and pycairo:

    python3 ~/.config/waybar/scripts/build-sisyphus-alternating.py
    python3 ~/.config/waybar/scripts/sisyphus-studies.py build

Use --large for 628x314 preview frames, then rerun without it to restore 160x80
Waybar assets. comparison.gif shows all three gait choices at a larger size.
foot-positions.json records sampled ankle positions for inspection.

Artwork generated using the built-in image-generation tool. Prompt specification:
A production cutout animation atlas matching the approved painted Greek Sisyphus,
with separate torso, near/far thighs, near/far calves and sandals, detailed warm
skin, cream cloth, brown sandals, right-facing pushing posture, transparent
background, no rock or ground. Parts have rounded joint ends for articulation.
The final background-extraction prompt was:

"Use case: background-extraction. Remove ALL the brown backdrop, glow, cast shadows,
and background between the six cutout pieces. Output genuine transparent alpha
background. Preserve exactly the six painted body parts, all their pixels, scale,
arrangement, anatomy and colors. Nothing else changes. Every pixel outside the
body parts must be transparent, no studio backdrop, no glow. These are animation
puppet parts to composite into software."
