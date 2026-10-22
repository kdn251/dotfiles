# Agent mascot artwork

Sisyphus is the live agent-status indicator at the start of Waybar's right group.
It pushes while a monitored agent is working, signals attention with a raised
hand, freezes and dims for unknown status, and hides when all sessions are idle.
Hover for counts, hosts, and activity age. The number beside the sprite is the
working count; an exclamation mark indicates waiting agents.

The activity service implementation and restore instructions are documented in
`agent-attention/README.md` at the repository root. The bar no longer enables
Calcifer or preview toggles. Those source assets remain available for future use.

The shaded SVG sprites run at 12 fps and use 32 logical pixels of height. Rebuild
all 96 frames and CSS with:

```sh
python3 ~/.config/waybar/scripts/build-agent-mascots.py
systemctl --user restart waybar.service
```

`agent-mascot.py` is an optional standalone artwork preview generator. The live
module uses `agent-status.py`; preview preferences have no effect on live status.
