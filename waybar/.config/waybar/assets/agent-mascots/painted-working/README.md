# Approved live Sisyphus A

The user approved stride-v9 A as the final working animation. These are exact
copies of its 96 PNG frames, played at 32fps in the real agent-status module.
manifest.json records the source and SHA-256 of every approved frame.

The indicator continues to use real local/remote agent lifecycle snapshots and
opens the existing agent panel. Idle/unknown states show a frozen first frame;
attention and the previously approved completion/check-mark pose keep their
existing artwork. Comparison A/B/C modules are no longer loaded in Waybar.

## Original mascot and rollback

The original 24-frame SVG mascot is preserved, unchanged, in the parent directory
(sisyphus-working-*.svg, sisyphus-attention-*.svg, sisyphus-complete-*.svg).
Its generator and agent-mascots.css are also preserved.

To restore the original mascot, append --classic to the custom/agent_sisyphus
exec in ~/.config/waybar/config.jsonc:

    python3 ~/.config/waybar/scripts/agent-status.py --classic

Then run:

    systemctl --user restart waybar.service

Remove --classic to return to approved A. This changes both frame selection and
playback cadence; no asset replacement is required.

## Rebuild / new machines

All final frames, styles, renderer and source illustrations are committed to the
Waybar dotfiles package. Stowing that package installs the final animation.
To reproduce the final frames from the painted source rig:

    python3 ~/.config/waybar/scripts/build-sisyphus-grip.py
    python3 ~/.config/waybar/scripts/build-sisyphus-live.py

The second command copies the approved frames and regenerates sisyphus-live.css
and the manifest. Dependencies for rebuilding are Python, Pillow and pycairo.
