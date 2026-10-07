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

#### shared AI skills and commands

The `agents` Stow package shares personal workflows across Pi, Codex, OpenCode,
and Claude Code. It contains instructions only, not credentials or session data.

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

