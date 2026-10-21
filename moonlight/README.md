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
   This profile was saved for the laptop-sized virtual display; it is not a
   matching-resolution profile for the physical 3840x2160 monitor. Review the
   stream resolution when using physical-display capture (see below).
   This command backs up the local configuration and merges only allowed preferences.
4. Open Moonlight, add `100.117.97.60`, and pair this client through Apollo's PIN page.
   Apollo may require granting Launch Apps and input permissions to the new client.
   Check the new client's **Always create virtual display** setting and turn it
   off for physical-monitor streaming. This is separate from the app-level switch.
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

## Desktop captures the physical main monitor (Apollo host settings)

The intended Desktop behavior is to show the PC's existing physical main monitor,
including its taskbar and open applications. Virtual-display streaming is optional,
not required for this setup.

On 2026-10-21, the assistant operating the Windows PC reported finding the
wallpaper-only Desktop cause: the **Kevin's Framework Laptop** pairing entry had
**Always create virtual display** enabled. It created and captured a 2880x1920
virtual screen while the apps remained on the physical monitor. The assistant
disabled and saved only that client-specific option. The resulting stream has
not yet been confirmed from the laptop.

Restore/check these settings in Apollo:

- Paired client **Kevin's Framework Laptop**: **Always create virtual display OFF**.
  Check this independently for every newly paired computer.
- Global Audio/Video: **Headless Mode OFF**; no explicit Output Name override.
- Applications -> Desktop: **Always use Virtual Display OFF**; no preferred-display
  override or startup commands. With no overrides, capture the primary display.
- Client display-mode override blank; no connect/disconnect commands.

The host inspection reported the primary physical monitor as **LG ULTRAGEAR+**,
`\\.\DISPLAY2`, **3840x2160 at 144 Hz**. Display identifiers can change, so do not
hard-code that identifier without checking the current display list. The unwanted
virtual display was reported as `\\.\DISPLAY5`.

After saving, end the old Apollo app session rather than merely disconnecting.
If Moonlight asks to quit the paused Steam Big Picture session when opening
Desktop, save any running game before accepting. Start a fresh **Desktop** session
and verify that the taskbar and existing windows are visible. The old session may
still retain its virtual display until it ends.

These are host-side settings documented for manual restoration; Stow does not
apply them. Do not copy Apollo's pairing database or private credentials into Git.
No stream-resolution change was made as part of this fix: the saved client profile
remains 2880x1920, 120 FPS, 80 Mbps. For physical-monitor capture, review the
resolution/aspect ratio separately; the host is 16:9 and the laptop is 3:2.
Test capture with the physical monitor powered off before depending on that use
case, since some monitors stop exposing a usable display when powered off.

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
