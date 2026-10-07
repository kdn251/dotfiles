# Clanker computer notification

Installed locally for Hyprland; versioned as the `computer-notification` Stow
package in the dotfiles repository. Uses Python 3.11+/PyGObject, GTK3,
GTK Layer Shell and Cairo; no new packages were needed on the original machine. Node is needed only to regenerate
frames from the reference TypeScript, not at runtime.

## Use

```sh
computer-notification preview       # silent six-second preview
computer-notification status        # connection status and observed Pi count
systemctl --user status computer-notification.service
journalctl --user -u computer-notification.service -f
```

The title is “Clanker is ready”, or “N Clankers are ready” for concurrent
completions. The title and a smaller project/tab line (e.g. `ferryman · tab 2`)
are centered to the right of the animation. Concurrent completions show the two
most recent entries plus a count for any others; long labels are ellipsized.
The preview uses metadata from the first connected agent (or a placeholder),
clearly marked `Preview:` rather than implying a real agent finished. Project
names come from the working directory and displayed tab names from Herdr's
`tab.list` API. Internal routing IDs such as `w9:t7` are never used as labels;
if a name is unavailable, only the project is shown.
A namespace-specific Hyprland layer rule makes the popup slide
in from the right and slide back out; other layers retain their existing styles.
“Ready” means settled/awaiting input, not guaranteed success.
Errors or an interrupted run can also settle. This does not infer task success.

## How it works

One local GTK application owns one non-focusing layer-shell overlay and one SSH
connection to `boole`. A transient Python script runs through authenticated SSH
and reads the existing private Herdr Unix socket. It is not installed on the
VPS and exits when the SSH stream closes (at the latest on its next heartbeat).
No TCP listener, terminal scraping, pane input, new extension, or server restart.

`bridge.py` subscribes to supported Herdr 0.9.3 pane lifecycle/state events.
Events invalidate state; `agent.list` snapshots are authoritative. A five-second
heartbeat also reconciles state and new panes. Only Pi agents with the official
`herdr:pi` session source and lifecycle authority are included. Your existing
VPS integration reports idle on Pi's `agent_settled` plus `ctx.isIdle()`; this is
not `turn_end`, `message_end`, or `agent_end` (which can precede continuation).

`state.py` deduplicates Herdr completion sequence numbers, scoped to pane,
terminal and Pi session. Herdr resets the optional sequence on working state;
a new idle/done completion has a fresh sequence. A fresh baseline is established
on startup/reconnect and new agent discovery; past completions are never replayed.
Very short work completed entirely while disconnected or before discovery may
be intentionally missed. Only currently settled agents produce a popup.

SSH is noninteractive, verifies hosts normally, has connection/keepalive timeouts,
and retries with bounded backoff. It does not reuse/kill your Herdr client's SSH
connection. Bounded queues and stale-stream rejection prevent backlog replay after
network stalls/sleep. The local control socket is private (0600 in a 0700 runtime
directory); it accepts only the fixed `preview` command. An advisory lock prevents
multiple daemon instances.

Original `macScene(38, elapsedMs)` artwork is sampled into `frames.json`: 38x26
source pixels at integer 5x scaling (190x130 logical pixels of art). Frames retain
the original palette and shapes. Timing starts late in travel, then shows insert,
read and happy phases. Cairo antialiasing is disabled for artwork. Hyprland's
monitor scaling applies afterward; the current monitor uses integer 2x scaling.

The popup does not call present(), grab keyboard focus, reserve screen space,
change workspaces, or dispatch Hyprland actions. Keyboard mode is NONE and the
pointer input region is empty, so it is click-through. Concurrent completions
share one popup and count; its maximum lifetime is twice the configured duration.
There is no unbounded queue of animations.

## Sound and existing notifications

This app has no audio code and makes no notification.show/notify-send calls.
Herdr remains responsible for the existing chime and its focus suppression.
Local `ui.toast.delivery = "system"` and VPS `delivery = "herdr"` were left
unchanged. Existing Herdr/swaync notifications may therefore coexist with this
popup. Global suppression would also remove other agents' and needs-input
alerts; it was deliberately not applied. Herdr's own sound behavior still
requires its local client and follows its current focus/notification policy.

## Configuration

Edit `~/.config/computer-notification/config.toml`, then:

```sh
systemctl --user restart computer-notification.service
```

Settings: SSH host alias, remote Herdr socket path, integer pixel_scale (2–10),
duration (4–15 seconds), margin_top and margin_right. Position is top right on
the compositor-selected monitor; margins are relative to available layer-shell
space (the top bar adds its reserved height). This custom popup does not inherit
swaync Do Not Disturb. Stop the service to suppress it temporarily.

## Autostart / installation

From the dotfiles checkout, deploy with GNU Stow:

```sh
stow --no-folding -t "$HOME" computer-notification
systemctl --user daemon-reload
systemctl --user enable --now computer-notification.service
```

Back up and reconcile existing files if Stow reports conflicts; do not use
`--adopt`. The installed files are symlinks to this package, so editing them also
updates the checkout. Keep the checkout in place. On another machine set the SSH
host/socket in the config, and ensure Python 3.11+, PyGObject, GTK3, Cairo and
GTK Layer Shell are installed. The original reference copies are not required.

Files:
- `~/.local/bin/computer-notification`: launcher
- `~/.local/share/computer-notification/`: implementation, original art, tests
- `~/.config/computer-notification/config.toml`: settings
- `~/.config/systemd/user/computer-notification.service`: user service
- `~/computer-notification-reference/`: inspected source/docs; optional archive

Enabled under your existing `hyprland-session.target`. Your Hyprland config
already imports Wayland variables into systemd before starting that target;
the popup's slide animation is configured by this scoped rule in
`~/.config/hypr/hyprland.conf`:

```ini
layerrule = animation slide right, match:namespace ^(computer-notification)$
```

It uses your existing layersIn/layersOut animation timing.

To re-enable after disabling:

```sh
systemctl --user daemon-reload
systemctl --user enable --now computer-notification.service
```

Ensure SSH `boole` works with BatchMode and normal known-host verification.
Use the appropriate graphical session target on another machine. If you do not
use this repo's `hypr` package, add the scoped slide rule above to your own config
and enable Hyprland animations.

Regenerate frames after changing the reference copy:

```sh
node ~/.local/share/computer-notification/generate-frames.mjs
systemctl --user restart computer-notification.service
```

## Verification

```sh
python3 -m unittest discover -s ~/.local/share/computer-notification -p 'test_*.py' -v
computer-notification preview
```

Automated tests cover original frame dimensions/phases, duplicate events,
intermediate working states, null/missing completion sequence, concurrent agents,
new/replaced/closed sessions and reconnect baselines.

Installation checks verified connection to the three existing lifecycle-reported
Pi agents, unchanged active Hyprland window/workspace during preview, automatic
layer dismissal, original-art rendering, concurrent preview coalescing, singleton
protection, and fresh connection baselines after the watcher's own SSH disconnect.

**Real completion / audible chime acceptance test still needs your participation:**
1. In an existing idle Pi on boole, ask it to reply briefly without tools.
2. Immediately switch to another desktop application.
3. Check for “Clanker is ready”, one existing Herdr chime (if Herdr's policy permits
   it), no focus/workspace change, and automatic dismissal.
4. Check whether Herdr also displays a redundant system/in-app toast. Report that
   before choosing a targeted suppression policy.

No prompt was injected into your existing agents to force this test.

## Uninstall

```sh
systemctl --user disable --now computer-notification.service
# Run from the dotfiles checkout; removes deployed links, not repository files.
stow --no-folding -D -t "$HOME" computer-notification
systemctl --user daemon-reload
rm -rf "${XDG_RUNTIME_DIR:?}/computer-notification"
# Optional: remove downloaded source/documentation reference copies.
# rm -r ~/computer-notification-reference
```

Remove the `# Clanker popup` comment and its `layerrule` line from
`~/.config/hypr/hyprland.conf` when uninstalling. There are no VPS changes to undo,
and no Herdr or swaync settings to restore.
