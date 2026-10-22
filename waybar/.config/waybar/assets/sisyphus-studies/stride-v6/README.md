# Live-mascot uphill pose studies

The current live vector mascot is the geometry reference, not the artwork style.
Its incline rises 20 units over 68 horizontal units (16.39 degrees), taken from
build-agent-mascots.py's ground path M5 39 L73 19. Earlier painted studies used
0.18 rise/run (10.20 degrees). All three new versions use the exact live incline.

The detailed atlas from ../stride-v4 is reused unchanged. The painted torso is
rotated substantially upright, hands push upward against the boulder, and both
feet and the rock contact calculation follow the steeper ground. The ground
texture is transformed to the same incline. Three poses compare:

- A: upright with a forward brace, torso rotation -0.40 radians.
- B: stronger upward push, -0.55 radians.
- C: most upright/highest hand placement, -0.70 radians.

All three preserve explicit alternating near/far leg animation, with 48px stride
amplitude, 23px recovery lift, 53% stance, and two cycles per three-second rock
rotation. The shorter stride is closer to the live mascot's compact climbing
steps. A small torso rock around fixed palms communicates repeated effort.
The far leg retains its subtle shadow. Sandals are oriented to the same slope.

Preserved: stride-v4/a (previous winning motion), stride-v5 (previous posture
round), and the original approved painted artwork. The live status mascot and
its completion animation are unchanged. These are preview modules only.

Rebuild with Python, Pillow and pycairo:

    python3 ~/.config/waybar/scripts/build-sisyphus-uphill.py
    python3 ~/.config/waybar/scripts/sisyphus-studies.py build

--large renders 628x314 frames for comparison.gif. Run normally afterward to
restore 160x80 playback frames. All source art dependencies live in sibling
stride-v4 and rolling-v2 directories. No new artwork generation was needed.
