    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║        ██╗  ██╗██████╗                                        ║
    ║        ██║ ██╔╝╚════██╗                                       ║
    ║        █████╔╝  █████╔╝                                       ║
    ║        ██╔═██╗ ██╔═══╝                                        ║
    ║        ██║  ██╗███████╗                                       ║
    ║        ╚═╝  ╚═╝╚══════╝                                       ║
    ║                                                               ║
    ║    ██████╗  ██████╗ ████████╗███████╗██╗██╗     ███████╗███████╗
    ║    ██╔══██╗██╔═══██╗╚══██╔══╝██╔════╝██║██║     ██╔════╝██╔════╝
    ║    ██║  ██║██║   ██║   ██║   █████╗  ██║██║     █████╗  ███████╗
    ║    ██║  ██║██║   ██║   ██║   ██╔══╝  ██║██║     ██╔══╝  ╚════██║
    ║    ██████╔╝╚██████╔╝   ██║   ██║     ██║███████╗███████╗███████║
    ║    ╚═════╝  ╚═════╝    ╚═╝   ╚═╝     ╚═╝╚══════╝╚══════╝╚══════╝
    ║                                                               ║
    ║                 🐧 arch linux setup script 🐧                 ║
    ║                                                               ║
    ║           install your dotfiles and packages                  ║
    ║              (press Ctrl+C to cancel anytime)                 ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
#### steps to set up new machine 
1. install arch linux with `archinstall` or manually or with [this video](https://www.youtube.com/watch?v=fFxWuYui2LI)
2. once installed open terminal and run - `curl -fsSL https://k2.codes/setup.sh | bash`
3. reboot machine for configs to be updated - `sudo reboot`
4. generate new ssh key - `ssh-keygen -t ed25519 -C "your_email@example.com"` and add it to github

#### File manager columns

To restore Name, Size, Type, and Date Modified in list view, close Thunar
and run `bash ~/dotfiles/scripts/scripts/restore-file-manager-columns.sh`
from your desktop session. This requires `xfconf-query` and `gsettings`.
The script saves fixed Thunar 4.20 column widths and a 1100×750 opening
window so the columns fit together. It also enables the same four columns
in Nautilus when installed. These desktop settings live outside Stow;
run the script once after a reinstall, not at every login.

#### OBS recording and Stream Deck recovery

The `scripts` and `systemd` Stow packages include the OBS/OpenDeck recovery setup
added in October 2026. This setup is specific to Kevin's Arch Linux/Hyprland
machine and `/home/knaught`; it is not a generic OBS installer.

Tracked components:

- `obs-camera-reconnect.lua` follows the Cam Link's permanent USB ID and updates
  the existing Sony V4L2 source when its Linux device number changes.
- `obs-display-follow.py` selects the focused, powered-on Hyprland display,
  fits it behind the camera overlay in the three desktop scenes, and rebuilds
  capture after display changes or a screen-sharing portal restart. It checks
  portal responsiveness and restarts an unresponsive Hyprland portal.
- `obs-display-bridge.lua` and `obs-display-create.c` create replacement PipeWire
  sources on OBS's UI thread, where desktop-portal replies are processed.
- `opendeck-watchdog.py` starts OpenDeck when the Stream Deck is connected and
  checks device ownership, the local OpenDeck WebSocket server, and the OBS
  plugin's connection. It allows startup/reconnect grace periods and limits
  recovery restarts to avoid restart loops. `opendeck.service` also restarts
  OpenDeck after it exits.

Restore on this machine:

1. Install OBS Studio, OpenDeck, Hyprland and its desktop portal, a C compiler,
   and the Python packages `psutil`, `websocket-client`, and PyGObject (`gi`).
   On Arch, the Python packages are `python-psutil`, `python-websocket-client`,
   and `python-gobject`. OBS headers and `libobs` must be installed for the build.
2. Reconcile existing files before linking the two Stow packages. From this
   repository, run `stow --no-folding -t "$HOME" scripts systemd`. Do not use
   `--adopt` to overwrite repository files with unrelated local versions.
3. Build the native bridge locally. The compiled binary is deliberately ignored:

   ```sh
   cc -shared -fPIC -Wall -Wextra -Werror -I/usr/include/obs \
     "$HOME/scripts/obs-display-create.c" \
     -o "$HOME/scripts/obs-display-create.so" -lobs
   mkdir -p "$HOME/.local/state/obs-display-follow"
   ```

   Rebuild the bridge after OBS ABI changes. Do not replace the loaded library
   while OBS is running; close OBS before rebuilding it.
4. In OBS, add `~/scripts/obs-camera-reconnect.lua` and
   `~/scripts/obs-display-bridge.lua` through **Tools → Scripts**. Keep the
   existing `obs-waybar-recording.lua` script if recording status is wanted.
   Enable OBS's WebSocket server with authentication. Its password remains in
   OBS's local config; the display helper reads it there.
5. Restore the recording choices in the current OBS profile:

   | Setting | Value |
   | --- | --- |
   | Output mode | Advanced |
   | Recording type | Standard |
   | Recording format | Hybrid MOV (`hybrid_mov`) |
   | Video encoder | QuickSync HEVC (`obs_qsv11_hevc`) |
   | Rate control / quality | CQP / 20 |
   | Keyframe interval | 2 seconds |
   | Audio encoder | FFmpeg PCM, 24-bit (`ffmpeg_pcm_s24le`) |
   | Sample rate / channels | 48 kHz / stereo |
   | Audio track | 1 |

   For the Sony V4L2 camera source, enable automatic reset on timeout and set
   the timeout to 120 frames. The saved device path is
   `/dev/v4l/by-id/usb-Elgato_Cam_Link_4K_A29YB53135TO7F-video-index0`.
   These are recording settings; streaming settings are separate.
6. In OpenDeck's Multi OBS Controller plugin, enter OBS's local WebSocket port
   and password. Leave OpenDeck's own autolaunch disabled because the watchdog
   manages startup. Restore button profiles from a separate private backup.
7. Activate the recovery services:

   ```sh
   systemctl --user daemon-reload
   systemctl --user enable --now obs-display-follow.service opendeck-watchdog.service
   ```

   Do not separately enable `opendeck.service`: the watchdog starts it when the
   deck appears. Once started, OpenDeck remains available in the background.

Machine-specific references to review after replacing hardware or recreating
OBS sources:

- The camera script targets source UUID `d2add3c9-9810-4a7b-9040-a95da43468af`
  (`sony cam (new)`) and the Cam Link ID above.
- The display helper targets `screen with cam`, `screen with cam with greenscreen`,
  and `laptop no monitor`. Its source is named `monitor (automatic)`; it replaces
  the old `monitor` source after a successful capture and disables the obsolete
  V4L2 `screen` item. Screen-sharing selections are stored locally through the
  desktop portal; tokens are never committed here.
- The deck watchdog recognizes USB vendor/product `0fd9:006d` and reads the
  selected profile for device `sd-AL28K2C85916`. Update these constants if the
  deck changes. It checks the local Multi OBS Controller connection only when
  the selected profile uses that plugin and OBS is listening.

Runtime OBS scene collections, OpenDeck profiles, WebSocket passwords, portal
tokens, and private rollback snapshots are **not** included in this Git backup.
The restore steps preserve the configuration choices without publishing those
files. A complete scene layout/button-profile restore still needs a private
backup of those application files.

Diagnostics:

```sh
journalctl --user -u obs-display-follow.service -u opendeck-watchdog.service -u opendeck.service
```

To disable the automation, run
`systemctl --user disable --now obs-display-follow.service opendeck-watchdog.service`,
then `systemctl --user stop opendeck.service`. Remove the two OBS recovery scripts
from Tools → Scripts if desired. Local pre-change snapshots are in
`~/.local/state/obs-display-follow/`, `~/.local/state/opendeck-recovery/`, and the
timestamped `before-*` files alongside the OBS profile and scene collection.

#### shared AI skills and commands

The `agents` Stow package shares personal workflows across Pi, Codex, OpenCode,
and Claude Code. It contains shared instructions and personal Pi extensions,
not credentials or session data. For the complete Pi setup, use the bootstrap
below instead of only Stow.

```sh
# From this repository, on a machine with GNU Stow installed:
stow --no-folding -t "$HOME" agents
```

Back up and reconcile existing files first if Stow reports conflicts. Do not
blindly delete existing harness directories or use `--adopt` to overwrite the
repository with machine-local files.

- `agents/.agents/skills/`: canonical skills, discovered directly by Pi, Codex,
  and OpenCode. Claude's per-skill symlinks point here through `~/.agents/skills`.
- `agents/.agents/commands/`: canonical slash-command prompts. Pi's
  `~/.pi/agent/prompts/` and OpenCode's `~/.config/opencode/commands/` link here.
- Skills: `push`, `pr-review`, `fix`, `feature`, `regression`, and `sentry`.
- Commands: `/fix`, `/feature`, `/regression`, `/sentry`, `/reset-video-post`.

Run `/reload` in Pi after changes. Skills are also available as `/skill:name`.
The `push` skill is explicit-only, so it is not advertised for automatic use.

These workflows retain their original instructions. Some are Ferryman-specific:
Sentry, Axiom, and production database tools must be configured separately.
`/fix` includes a branch push and PR; `/reset-video-post` generates SQL for human
review and must not execute production mutations. Claude-specific skill metadata
such as `context: fork` is not guaranteed to work in other harnesses.
Project-local Ferryman copies are preserved and can override the shared versions
in OpenCode; update or reconcile them deliberately when changing a workflow.

#### Reproduce the Pi setup on a new machine

Install Git, Python 3.10+, Node.js 22.19+ with npm, and Pi. These preferences and
extensions are tested with Pi **1.0.4**; exact third-party plugin versions are
recorded in [`pi-config.json`](pi-config.json).

```sh
# One way to install the tested Pi version (or use Pi's official installer):
npm install -g --ignore-scripts @earendil-works/pi-coding-agent@1.0.4

git clone git@github.com:kdn251/dotfiles.git ~/projects/dotfiles
cd ~/projects/dotfiles
python3 setup-pi.py
pi
# In Pi: /login, then choose your provider/model.
```

On a machine without GitHub SSH keys, clone with
`https://github.com/kdn251/dotfiles.git` instead. The checkout can live anywhere;
setup computes the links for that machine. Keep the checkout in place afterward,
or rerun/reconcile its links if you move it.

The bootstrap:

- Links only the resources listed in `pi-config.json`, including shared skills,
  commands, the compact footer, Calm, and the Macintosh animation. It supports
  existing Stow directory links as well as individual file links.
- Merges `hideThinkingBlock` and `quietStartup` into local settings without
  replacing unrelated preferences. The question-layout extension defaults to
  inline questions unless `PI_ASK_USER_DISPLAY_MODE` is explicitly set.
- Installs pinned `pi-herdr`, `pi-web-access`, and `pi-ask-user` versions through
  `pi install`, which records them in local settings. An explicit override pins
  web-access's MCP SDK to the audited version; setup also runs `npm audit`.
- Enables Calm on first setup, preserving an existing on/off choice.
- Backs up replaced local settings or identical files to a private
  `~/.pi-config-backup-*` directory. Different existing resource files cause a
  conflict error rather than being overwritten. Resolve those deliberately.

**Never copy the entire `~/.pi` directory into Git.** Auth tokens, sessions,
model caches, installed npm trees, device IDs, generated Herdr hooks, and mutable
settings stay machine-local. `.gitignore` also guards the Pi runtime directory.
`pi-config.json` contains only shareable preferences; the bootstrap applies them
rather than symlinking the mutable `settings.json` into the repo. Local backups
may contain private settings, so keep them out of Git too.

This reproduces the chosen configuration and direct plugin versions, not a
byte-identical system image: npm's other transitive dependencies are not locked
in this repo. Pi's version is documented, not installed or downgraded by setup.
Logins, optional search API credentials, project tools, and the Herdr executable
and its host integration still need separate setup. Existing machine-generated
`herdr-agent-state.ts` is preserved, not copied to other machines. Ferryman-only
skills also need their project integrations separately.

For later updates, pull from `main`, rerun `python3 setup-pi.py`, and `/reload`
inside Pi. It is safe to rerun; `--skip-packages` links resources and applies
preferences without reinstalling plugins. A failed npm/audit step exits nonzero;
resolve the reported issue and rerun (earlier steps are not rolled back).

```sh
# Verification (the UI smoke test additionally requires tmux and Pi):
python3 -m unittest discover -s tests -p 'test_pi_*.py'
python3 tests/check-pi-animation.py
```

#### Pi calm display

`agents/.pi/agent/extensions/calm.ts` adds a lightweight `/calm` toggle using
Pi's tool-renderer API (tested with Pi 1.0.4). It starts enabled and hides normal
tool-call and result rows without replacing tool execution. Errors, `ask_user`
prompts/results, assistant replies, the standard working spinner, and the footer
remain visible. Tool images and user-bash rows can remain visible too.

- `/calm off`: restore stock tool rendering.
- `/calm on`: hide tool activity again.
- `/calm`: toggle; the command reloads extensions to rebuild existing rows.

The choice persists locally in Pi's agent directory as `calm.json`, not in Git.
Thinking visibility is separately controlled by Ctrl+t / `hideThinkingBlock`.
This is not the Firstmate extension: no boat animation, narration filtering,
operational-message filtering, or execution overrides are installed. Messages
and tool results remain in session storage. Turn Calm off before exporting if
you want stock tool rendering in the exported transcript.

#### Pi footer and activity animation

The compact footer shows model, thinking level, estimated session-branch cost,
and context usage. `/default-footer` restores the built-in footer until reload.
The standard editor and Working spinner are not replaced.

While Calm is enabled, a shaded pixel-art Macintosh and floppy delivery scene
plays during the wait for a response. It disappears on the first streamed text,
not when the completed response finishes. Thinking and tool-argument deltas do
not dismiss it. The scene uses 13 rows and falls back to a text label in very
narrow panes.

- `/calm-animation mac`: preview for 20 seconds and select the Macintosh scene.
- `/calm-animation off`: disable animation until reload.
- Other retained experiments: `robot`, `coffee`, `cat`, `rain`, `pong`, `cpu`, `both`.

Animation selection is intentionally session-local; reload defaults to `mac`.
Run `/reload` only after the current response has finished.

#### Clanker desktop completion popup

The `computer-notification` Stow package displays the original pixel-art Macintosh
next to **“Clanker is ready”** when a remote Pi agent settles. It slides in/out
from the right without stealing focus, dismisses automatically, and coalesces
concurrent completions. Blocked Pi agents show **“Clanker needs attention”**.
It adds no sound; the existing local Herdr client keeps handling chimes. The
`herdr` package sets `ui.toast.delivery = "off"` and `ui.sound.enabled = true`
to avoid duplicate Herdr popups. Merge those settings into independent local
Herdr configs and reload Herdr. This disables all Herdr visual toasts; Clanker
currently covers Pi on boole, not other agent types.

Requires Python 3.11+, GTK3, PyGObject, Cairo, gtk-layer-shell, SSH, and Hyprland.
On Arch the UI dependencies are `python-gobject python-cairo gtk3 gtk-layer-shell`.
Herdr 0.9.3 must already be running on `boole`, with its official Pi integration.
SSH must work noninteractively with normal known-host verification. No VPS changes
or exposed network listener are installed by this package.

```sh
# Review/reconcile conflicting local files first; do not use --adopt.
stow --no-folding -t "$HOME" computer-notification
# Review ~/.config/computer-notification/config.toml (host, size, duration).
systemctl --user daemon-reload
systemctl --user enable --now computer-notification.service
computer-notification preview
computer-notification status
```

The service starts with this repo's `hyprland-session.target`. The `hypr` package
contains the namespace-specific slide rule; animations must be enabled. If you
use your own Hyprland configuration, copy the rule from the detailed guide rather
than replacing your entire desktop configuration. Pre-generated frames are
included, so Node is needed only when regenerating the original TypeScript art.

[Detailed usage, architecture, testing, and uninstall instructions](computer-notification/.local/share/computer-notification/README.md).
Runtime sockets, logs, connection baselines, downloaded reference docs, private
backups, SSH credentials, and Python bytecode are not part of this package.

#### general notes
1. remember to always deploy personal website when `setup.sh` script changes so that newest changes can be reflected if setting up a new machine
2. might need to run `sudo stow -t /etc keyd` since `/etc` requires sudo and keyd needs to live in `/etc` not `~/` 
3. Copy my `~/.zshrc` file from another machine directly/safely since it has credentials in it
4. Probably need to run `sudo stow -t / root-etc` to stow files in `/etc` correctly (maybe can add this to startup script as well)
5. Probably need to update `/etc/udev/rules.d/99-powertuning.rules` to include
```
# Set performance profile when AC adapter is plugged in
SUBSYSTEM=="power_supply", ATTR{online}=="1", RUN+="/usr/bin/powerprofilesctl set performance"

# Set power-saver profile when AC adapter is unplugged
SUBSYSTEM=="power_supply", ATTR{online}=="0", RUN+="/usr/bin/powerprofilesctl set power-saver"
```

#### helpful notes
1. if `ly` fails to get enabled run `sudo systemctl enable ly@tty2.service` and then `sudo systemctl set-default graphical.target` and `sudo reboot`
2. if `yay` failed to successfully installs the `AUR` packages run `yay -S --needed --noconfirm - < ~/dotfiles/aur-packages.txt` manually
3. probably need to manually install localsend just figure out how to do that with `yay` and the `AUR`
4. probably need to manually install Steam just figure out how to do that with `yay` and the `AUR`
5. probably need to manually install davinci resolve as well just figure out how to do that with `yay` and the `AUR` (removed it since it manually compiles a massive library qt5-location which slows down setup for new machines massively)
6. set up powertop on new machine
```
# 1. Install the package
sudo pacman -S --needed powertop

# 2. Create the service file
sudo tee /etc/systemd/system/powertop.service <<EOF
[Unit]
Description=Powertop tunables autotuner

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/powertop --auto-tune

[Install]
WantedBy=multi-user.target
EOF

# 3. Reload, enable, and start
sudo systemctl daemon-reload
sudo systemctl enable --now powertop.service
```

#### old/archived notes that may help with debugging but shouldn't be actively used
1. Run `pacman -Qqm > aur-packages.txt` to update list of AUR installed packages
2. Run `crontab -l > ~/dotfiles/crontab_knaught` to get up to date crontab file to push to repo and pull down on other machines. On other machines run `crontab ~/dotfiles/crontab_knaught` (or wherever the file lives) to recreate the cron jobs on the new machine
3. Start all necessary services I rely on with `sudo systemctl starts SERVICE_NAME` (still need to gather this list of services and place them in a script to start the all)

