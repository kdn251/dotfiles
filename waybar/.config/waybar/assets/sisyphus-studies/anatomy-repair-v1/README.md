# Anatomy repair — review draft

Requested after enlarged inspection of the approved stride-v9 preview exposed
extra painted limb stubs and overlapping ankle pieces. This is a separate review
artifact, not installed into the live Waybar module.

New comparison file: ../stride-v9/preview-anatomy-v2.gif
Original preserved: ../stride-v9/preview.gif

Changes:
- New torso source contains no arms, hands, thighs or feet beneath the cloth.
- Exactly two arm chains are composited from one isolated upper-arm source and
  one continuous forearm/hand source. No arm is retained in the torso artwork.
- Exactly two thigh/calf chains. The calf, ankle and sandal are a single skinned
  surface; the old independently overlaid shoe pieces are not used.
- A controlled heel lift/toe-off replaces the always-flat-foot constraint.
  Ground support is calculated from actual sandal pixels, not a rectangular box.
- Raised hip placement and adjusted torso proportions give the legs more room.
- Shoulder/elbow/knee overlaps are feathered to remove hard cutout joint borders.

The 16.39-degree slope, painted boulder, alternating steps, and staggered hand
motion remain. The figure is checked at full preview resolution, not just Waybar
size. This remains an illustration animation draft for visual review.

Sources torso.png and arm-parts.png were made with the built-in image-generation
tool. Exact prompts are retained in generation-prompts.txt. Other source art is
reused from stride-v4 and rolling-v2 without modifying those directories.

Rebuild (Python, Pillow and pycairo):

    python3 ~/.config/waybar/scripts/build-sisyphus-anatomy-repair.py

This renders 96 frames at 1256x628 into ignored frames/. Export at 32fps to the
comparison GIF; no production CSS, status scripts or config are changed.

## Motion v3 review

`../stride-v9/preview-motion-v3.gif` preserves v2 alongside the new version.
Rebuild with `scripts/build-sisyphus-motion-v3.py` relative to the Waybar root.
The ankle mesh interpolates rotation rather than collapsing between two
transforms; foot pitch follows the shin within 0.35 radians and ground contact
is recalculated. Both wrists flex by 0.12 radians with staggered timing.
Loose hair moves with a localized mesh deformation; the face stays anchored.
All 96 frames render successfully. Live Waybar assets remain unchanged.
