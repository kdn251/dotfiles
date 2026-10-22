# Painted Sisyphus rolling trial

Study B. Approved A remains unchanged under ../painted/ and in git commit 44e8952.
Do not overwrite that approved source when iterating.

ImageGen separated the approved illustration into a foreground eight-frame sheet
and an isolated stone. build-sisyphus-rolling.py composites those layers, rotates
the stone through 360 degrees, and adjusts its height against an inclined support
line. The figure's existing eight-frame gait repeats three times per stone turn.
96 rendered frames play at 32 fps (three-second loop); the frame following 95 is 0.
Hands are composited in front of the rock. This is a working animation draft.

Rebuild with python3 ~/.config/waybar/scripts/build-sisyphus-rolling.py.
Use --large for 628px renders when exporting a full-size GIF, then run without it
to restore the lightweight 160px Waybar frames. preview.gif is the larger review copy.
