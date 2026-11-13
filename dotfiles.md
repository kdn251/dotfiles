# Restoring Kevin's desktop

This is the canonical new-machine runbook, audited against the current machine on
2026-11-13. The repo can rebuild the **public Arch/Hyprland desktop configuration**.
It cannot by itself reproduce the exact current machine: private application state,
local software, hardware configuration, and data are not all in Git. For a literal
identical system, keep a separate encrypted full-system backup as well as this repo.

## Before testing on a new machine

1. Review, commit, and push the intended configuration changes, including existing
   work in desktop configuration and its supporting scripts. A fresh clone cannot
   see local changes. Do not include
   `*.before-*`, `.uuid`, secrets, logs, or runtime databases. No
   website deployment was performed as part of the initial audit; the setup work
   is published separately through Git.
2. Make and verify the private backup described below. **No private backup was
   created by this audit.** A Git clone is not a replacement for that backup.
3. Use a spare machine or VM. The installer upgrades packages and configures
   services; use `--check` for a read-only audit of the current machine.
4. Install x86_64 Arch Linux first, with networking, a bootloader, working sudo,
   and a regular account named `knaught`, home `/home/knaught`. Use a unique hostname.
   Disk partitioning, encryption, bootloader installation, and Wi-Fi credentials
   are outside this script. Other operating systems and account names are not
   supported by the current configs.
5. Enable these two lines in `/etc/pacman.conf` (needed for Steam/32-bit graphics):

   ```ini
   [multilib]
   Include = /etc/pacman.d/mirrorlist
   ```

## One-command public setup

Run as `knaught`, **not root**, from the installed Arch system:

```sh
sudo pacman -Syu --needed git python && git clone https://github.com/kdn251/dotfiles.git ~/dotfiles && bash ~/dotfiles/setup.sh
```

If the checkout already exists, inspect it and run:

```sh
bash ~/dotfiles/setup.sh
```

Sudo, package conflict/provider, and AUR build prompts are expected. This is one
entry point, not a promise of unattended installation. AUR build/download failures
stop the script. Fix the displayed problem and rerun; completed steps remain.
Never run it through `sudo bash`, `stow */`, or `stow --adopt`.

The installer:

- Performs a full Arch upgrade and installs the explicit package snapshots plus
  the required build/runtime dependencies in `bootstrap/packages.txt`.
- Builds yay if needed and installs foreign-package names through yay. It excludes
  `-debug` outputs, which are build byproducts. Foreign packages may disappear or
  cease to be available from AUR; package versions are not frozen.
- Checks Stow conflicts before linking only `bootstrap/stow-packages.txt` packages.
  The CLI ignore patterns exclude tests, documentation, backup files, and generated
  service enablement links. Existing conflicting files are preserved; resolve the
  reported paths deliberately and rerun.
- Rebuilds the patched Waybar and Newsboat, installs the article extraction venv
  and MPV emoji font, and compiles the OBS native bridge. Close OBS before reruns.
- Applies Pi preferences/plugins with `setup-pi.py` and installs Agent Attention
  hooks. Pi itself comes from `pi-bin`; its available version may differ from the
  documented tested 1.0.4. Authentication remains separate.
- Copies selected keyd, timezone, power-profile and OpenCode hook files to `/etc`
  and `/usr/local`, backing up replaced files in `/var/backups/dotfiles.*`.
- Enables the system/user services listed in `bootstrap/`, configures Ly on tty2,
  selects zsh, and merges desktop cron jobs while preserving unrelated jobs.
  Existing cron data is backed up under `~/.local/state/dotfiles/`.
- Does **not** newly enable the cron jobs that automatically commit/push package
  snapshots. Existing copies of those jobs are preserved on reruns.
- Enables charge thresholds and Powertop only on Framework hardware. It disables
  enabled TLP/auto-cpufreq services to avoid fighting power-profiles-daemon.

The checkout stays at `~/dotfiles`: many scripts and links depend on that location.
The account restriction is intentional until the hard-coded home paths throughout
these configs are ported. Cron runtime paths are adapted to the actual UID.

### Website shortcut

On 2026-11-13, `https://k2.codes/computer.sh` returned HTTP 404.
`https://k2.codes/setup.sh` returned HTTP 200, but its contents differed from the
repository installer. Deploy **`scripts/scripts/setup.sh`** to the website's
`/setup.sh` route after the Git changes land. It is now a small bootstrap that
clones this repo and delegates to `bootstrap/restore.sh`; installer logic stays here.

Verify the deployed file matches before advertising this shortcut again:

```sh
curl -fsSL https://k2.codes/setup.sh -o /tmp/k2-setup.sh
cmp ~/dotfiles/scripts/scripts/setup.sh /tmp/k2-setup.sh
```

Then the website command is:

```sh
curl -fsSL https://k2.codes/setup.sh -o /tmp/k2-setup.sh && bash /tmp/k2-setup.sh
```

Downloading first keeps terminal input available for installation prompts. Keep
using the direct Git command until the website is deployed and verified.

## After installation

Reboot (`sudo reboot`), log into Hyprland, close Thunar, and run:

```sh
bash ~/dotfiles/setup.sh --desktop
```

This applies the saved file-manager columns and activates Agent Attention hooks
and service. Log out/in afterward to start the other enabled session services.
Then complete these items:

- Restore private app state from your backup while the apps are closed. Do not
  overwrite Stow links with an indiscriminate extraction of all of `.config`.
- Sign into 1Password, browsers, VPN, Tailscale, AI tools, and other accounts.
  Generate this machine's SSH key and authorize it on GitHub, boole, and Turing;
  verify host keys. The repo only carries SSH connection configuration.
- Follow [Moonlight](moonlight/README.md) for preferences and per-client pairing,
  and [Agent Attention](agent-attention/README.md) for display/game calibration.
- Restore OBS scenes/profiles and OpenDeck profiles/plugins. Follow the detailed
  [OBS recovery section](README.md#obs-recording-and-stream-deck-recovery) to load
  the Lua scripts, enable the WebSocket server, and reconnect the controller.
- With Brave closed, run
  `python3 ~/scripts/newsboat-install-browser-reading.py` to register the native
  reading host. This merges Brave flags; the flags file is shared through Stow,
  so review any resulting Git diff.
- Restore NVM/other language environments only if needed. The shell now uses the
  installed Arch Node/npm when NVM is absent; project dependencies are separate.
- Install the original machine's Flatpaks: `com.makemkv.MakeMKV` and
  `org.jellyfin.JellyfinDesktop` from Flathub, and `com.nvidia.geforcenow` from
  NVIDIA's GeForceNOW remote. Those installations and their app data are not
  managed by the bootstrap. The observed NVIDIA remote URL was
  `https://international.download.nvidia.com/GFNLinux/flatpak/geforcenow_repo`;
  use its official installer to configure signing and remote metadata.

## Private backup: required for the same working state

Use your encrypted backup system and verify a restore into a temporary directory
before relying on it. Close applications first so SQLite databases and profiles
are consistent. Keep backups outside this public repository. Do not commit any of
these directories wholesale:

| State | Backup/restore scope |
| --- | --- |
| OBS | `~/.config/obs-studio/` (scenes, profiles, WebSocket credentials) |
| OpenDeck | `~/.config/opendeck/`, `~/.local/share/opendeck/` (profiles/plugins) |
| Browser profiles | `~/.config/BraveSoftware/`, `~/.config/google-chrome/`, `~/.mozilla/`, and other browsers you use; prefer browser sync where appropriate |
| Shell secrets | `~/.config/zsh/secrets.zsh` if used; the tracked `.zshrc` sources it conditionally (absent on the audited machine) |
| Credentials | SSH/GPG keys, password-manager recovery material, keyrings; generate fresh device identities where supported |
| AI tools | Selected settings, custom skills/plugins, and needed sessions under `~/.codex/`, `~/.claude/`, `~/.pi/`, `~/.config/opencode/`, `~/.local/share/opencode/`; reauthenticate rather than publishing tokens |
| Dictation | `~/.local/share/hex/`, `~/.config/voxtype/`, `~/.local/share/voxtype/`, `~/.local/share/com.pais.handy/` (settings/models/account data) |
| Newsboat and streams | Private `.newsboat` databases/credentials, saved progress/libraries, `~/.local/share/newsboat/`, `~/.config/stream-player/`, download directories and relevant `~/.local/state/` data |
| Cloud/sync | `~/.config/rclone/`, Syncthing state, cloud mount credentials; reconfigure per-machine identities |
| Other applications | `~/.var/app/` Flatpak data, relevant `.config`/`.local/share` directories, Steam/game saves, chat clients, Obsidian vaults |
| Work and media | `~/projects/`, `~/Documents/`, pictures, music, videos, software and externally mounted data; Git remotes do not include uncommitted work |
| Local software | Record tools under `.local/bin`, `.local/libexec`, `/usr/local`, NVM/Cargo and language environments; rebuild/install for the destination rather than copying incompatible binaries |
| System recovery | Privately back up `/etc`, boot/encryption recovery information, package/version inventory, storage mounts and service overrides; selectively restore for new hardware |

The current machine has additional non-Git state, including a standalone
`~/.local/bin/yt-dlp`, custom Codex workflows/plugins, browser and app profiles,
and a local network monitor. This audit did not export or validate those private
backups. The public bootstrap is not a complete replacement for them.

## Hardware and network review

- Choose GPU drivers/firmware for the destination. The package snapshot includes
  both AMD/Intel microcode and Intel graphics packages; it is the original machine's
  inventory, not a universal NVIDIA/AMD GPU configuration.
- Review `kanshi`, Hyprland outputs/scales, audio devices, Cam Link IDs, and OBS
  source UUIDs. The current Hyprpaper/Hyprlock files were captured from the live
  machine during this audit; wallpapers/fonts are tracked.
- Framework charging uses BAT1 and 75/80 thresholds, guarded by a sysfs condition.
  Inspect the new laptop's battery path and confirm the service actually applies.
- USB wake/autosuspend rules and the old `enable-usb-wake` service are not applied
  globally. The latter toggles a specific ACPI device and is unsuitable as a
  generic repeatable restore step. GRUB power flags are also hardware-specific.
- The homelab mount timer/helper are tracked but deliberately not enabled by the
  bootstrap: restore mount definitions, reachability, and private credentials first.
- The original machine's `rclone-gdrive`, Syncthing, and network monitor units are
  not all enabled in the current live state; legacy service lists are not the
  restore source of truth. The authoritative enabled desktop baseline is in
  `bootstrap/system-services.txt` and `bootstrap/user-services.txt`.

## Verification and recovery

```sh
bash ~/dotfiles/setup.sh --check
systemctl --failed
systemctl --user --failed
```

`--check` reports missing packages, Stow conflicts, required local assets, service
enablement, and unpublished changes. It exits nonzero when it finds issues. It is
read-only; a conflict-free Stow simulation does not prove every file is linked,
and asset existence does not prove ABI compatibility or a working desktop.

Smoke-test: log in through Ly, open a terminal, test audio/microphone and networking,
click Waybar workspaces, suspend/resume, open Newsboat and play a video, record a
short OBS clip, test OpenDeck and dictation, and pair/start Moonlight. Repeat on
the actual target hardware before calling it restored.

On a Stow conflict, inspect both files, save the local one outside the destination
path, and rerun. Do not use `--adopt` to silently replace repository configuration.
System-file rollback copies are printed by the installer; prior crontabs are under
`~/.local/state/dotfiles/`. There is no automatic transaction rollback for package
installations or completed steps, and the installer never automatically reboots.

Repository checks (no package installs or live-system changes):

```sh
python3 -m unittest discover -s tests -p test_bootstrap.py -v
python3 -m unittest discover -s tests -p 'test_pi_*.py'
bash -n scripts/scripts/setup.sh bootstrap/restore.sh bootstrap/system.sh post_install.sh
```

A disposable-home Stow install/rerun and conflict-preservation tests cover the
linking workflow. Full Arch/AUR installation, source builds against future package
versions, and a clean-machine graphical boot still need the planned new-machine
test. Do not treat those as already verified.
