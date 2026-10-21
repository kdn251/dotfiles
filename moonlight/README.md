# Moonlight and Play on PC

This Stow package installs the **Play on PC** launcher, its wake relay configuration,
and an explicitly applied Moonlight preference profile. The launcher contacts Turing
over Tailscale/SSH, sends three local Ethernet magic packets, waits up to three
minutes for Apollo's TCP port, and opens Moonlight. It skips waking an already
reachable PC. Turing needs Python 3 and must remain awake on the home LAN.

## Restore on another Arch computer

```sh
sudo pacman -S --needed moonlight-qt tailscale openssh python libnotify stow
sudo systemctl enable --now tailscaled
sudo tailscale up
cd ~/dotfiles
stow --no-folding -t "$HOME" moonlight
```

Back up any conflicting files before Stow; do not overwrite a live Moonlight
configuration with a repository copy. The main dotfiles setup installs the packages
and stows this directory too, but Tailscale login and pairing remain manual.

1. Authorize this computer's own SSH key for `knaught` on Turing. Never copy a
   different client's private key. Establish SSH once interactively and verify
   Turing's host fingerprint using a trusted source:
   `ssh -o HostName=100.74.35.69 knaught@turing`.
2. Check passwordless access with
   `ssh -o BatchMode=yes -o HostName=100.74.35.69 knaught@turing true`.
3. With Moonlight closed, run `~/.local/bin/moonlight-apply-preferences` if you want
   the saved profile: **2880x1920, 120 FPS, 80 Mbps**, automatic codec/decoder,
   SDR. Change resolution, FPS, and bitrate for the new computer's display/network.
   This command backs up the local configuration and merges only allowed preferences.
4. Open Moonlight, add `100.117.97.60`, and pair this client through Apollo's PIN page.
   Apollo may require granting Launch Apps and input permissions to the new client.
5. Search for **Play on PC** in your application launcher.

`~/.config/play-on-pc/connection.json` contains the host/relay addresses, relay user,
Ethernet MAC, and LAN broadcast address. Update it if the network changes. These
are connection details, not authentication secrets. The desktop entry uses the
current user's home directory rather than a fixed `/home/knaught` path.

Diagnostics (no shutdown):

```sh
~/.local/bin/play-on-pc --check       # Only check Apollo's port
~/.local/bin/play-on-pc --no-launch   # Wake and wait, without opening Moonlight
```

Moonlight's actual `~/.config/Moonlight Game Streaming Project/Moonlight.conf`
contains private keys, certificates and host pairing data. It stays local and is
gitignored. The saved JSON contains preferences only. Do not stow the live file.
The Hyprland Stow package also includes an opaque-window rule for Moonlight.

## Shut Down PC tile (configured on the Windows host)

This tile belongs to Apollo and will appear on newly paired clients automatically;
it is not a Moonlight client preference. In Apollo's web UI at
`https://localhost:47990`, add an application named **Shut Down PC**, leave its main
Command empty, and add this Detached Command:

```powershell
powershell.exe -NoProfile -STA -WindowStyle Hidden -Command "Add-Type -AssemblyName System.Windows.Forms; if ([System.Windows.Forms.MessageBox]::Show('Shut down the gaming PC now? Save your game first.', 'Shut Down PC', 'YesNo', 'Warning', 'Button2') -eq 'Yes') { shutdown.exe /s /t 0 }"
```

Save, select the tile in Moonlight, and click Yes in the streamed confirmation
dialog only after saving your work. No cancels shutdown. The command does not
force applications closed. Keep shutdown explicit rather than tied to stream
disconnects. The BIOS/Windows wake settings and Apollo virtual display setup are
host-specific and are not managed by these dotfiles.
