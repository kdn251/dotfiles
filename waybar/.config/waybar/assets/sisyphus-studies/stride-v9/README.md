# Cupped-hand refinement of winning A

Refines only stride-v8 A; the previous A is preserved at commit 93e23a1.
Both palm contact points sit a few pixels closer to the rock, and a localized
native animation-mesh bend turns the palms/fingers inward around their wrists.
The head, arm timing, body pose, slope, painted sources and alternating leg motion
are unchanged. The same cupped-hand texture is used for the separate rear arm.
Only preview slot A uses this version; B and C remain from stride-v8.

Rebuild with Python, Pillow and pycairo:

    python3 ~/.config/waybar/scripts/build-sisyphus-grip.py
    python3 ~/.config/waybar/scripts/sisyphus-studies.py build

--large generates 628x314 frames for preview.gif. Rerun normally afterward to
restore 160x80 Waybar playback frames. No new raster artwork was generated.
