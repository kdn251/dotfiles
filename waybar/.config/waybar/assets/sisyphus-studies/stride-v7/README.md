# Moving hands and arms on the winning uphill A pose

All three variants retain stride-v6 A's body pose, exact incline, leg lengths,
footpaths, cadence and painted sources. The previous A remains unchanged in
../stride-v6/a at commit 41e3641. This round compares arm motion only:

- A: controlled press, 24px total vertical palm travel.
- B: stronger elbow flex, 30px total palm travel.
- C: higher hand reposition, 40px total palm travel.

A native Cairo textured triangle mesh articulates the original painted elbows,
wrists and hands independently of the body. Smooth localized joint weights keep
the head and pelvis anchored. The fingers and palms move together. A contour
intersection of the rotating painted boulder determines palm horizontal position
at each frame, keeping the moving hand near its surface. Elbow compression is
phased with the pushing motion. No new raster artwork was generated or painted.

The animation has 96 frames at 32fps, two alternating gait cycles per stone
revolution. Each arm press takes 24 frames. Far and near leg paths remain a
half gait cycle apart. The 20/68 incline matches the live vector mascot.

These are review modules; the real live status mascot is unchanged. Earlier
versions and the original approved illustration remain intact.

Rebuild with Python, Pillow and pycairo:

    python3 ~/.config/waybar/scripts/build-sisyphus-pushing.py
    python3 ~/.config/waybar/scripts/sisyphus-studies.py build

--large produces 628x314 preview frames for comparison.gif. Rerun without it
for 160x80 Waybar assets. Source dependencies remain in stride-v4 and rolling-v2.
