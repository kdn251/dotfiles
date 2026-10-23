# Moonlight on the Samsung QN90D

This laptop uses its TV workspace 7 for Moonlight. The Hyprland config selects
3840x2160 at 60 Hz for the QN90D and makes Moonlight game streams fullscreen; the launcher remains tiled. The local
desktop entry starts `~/scripts/moonlight-launch.sh`, which gives Moonlight's
menu 0.65x Qt scaling on top of the TV’s 2.4x desktop scaling, selects the TV audio output, and returns the menu to workspace
7 after a stream ends. On the laptop without the TV, the launcher leaves the
normal menu scale and audio selection alone.

The current Moonlight streaming preferences are 3840x2160, 60 fps, 80 Mb/s,
automatic video codec and decoder, V-Sync on, frame pacing off, HDR off, and
prevent display sleep while streaming on. Moonlight stores these preferences
together with pairing credentials and a private key in its user config, so
that file must remain private and must not be committed to this repository.
The launcher and Hyprland settings supply the TV-specific behavior; Moonlight's
stream preferences can be adjusted in its settings menu.

## Recover from SSH

Run `~/scripts/tv-moonlight-restore.sh` as this desktop user. It finds the
running Hyprland session, restores the TV's 4K60 mode, selects TV audio, tries
to reconnect the paired 8BitDo controller if it is powered on, and starts or
refocuses Moonlight on workspace 7. It does not close a running stream.

The Samsung TV's Game Mode is set on the TV, not by this laptop. Leave it on
for the HDMI input used by the laptop, and check its Game Bar if latency rises.

If a streamed game appears as a small window inside Moonlight, change that
game's display mode and resolution on the gaming PC. The laptop's Moonlight
window is already fullscreen; its setting does not control the game's own
window on the PC.

The Samsung kanshi profile disables the built-in display while docked and uses
240% scaling on the TV. Unplugging the TV restores the laptop display.

Desktop refresh: shared Waybar, SwayNC, Bluetooth panels, fonts and Sisyphus
assets are synced with main. Install `swaync python-pillow bluetui` with pacman
and use the agent-attention installer from its README to restore the service.

## Recreate Turing's desktop

Install `swaync python-pillow bluetui python-gobject python-cairo gtk3
 gtk-layer-shell python-websocket-client waybar stow` with pacman. Link the
`hypr`, `kanshi`, `waybar`, `scripts`, `swaync`, `fuzzel`, `fonts`, `gtk-3.0`,
`kitty`, `xsettingsd`, `dbus`, `systemd`, and `desktop-files` packages using Stow.
Back up conflicting files before replacing them. Run the agent-attention
installer described in its README, then reload the user systemd manager.

Turing's TV-only idle behavior is deliberately separate from the default laptop
idle configuration. On Turing only, replace the existing hypridle config link:

```sh
ln -sfn "$HOME/dotfiles/hypr/.config/hypr/hypridle-turing.conf" "$HOME/.config/hypr/hypridle.conf"
systemctl --user restart hypridle.service
```

This keeps automatic locking enabled on other laptops. Turing's Samsung profile
in kanshi supplies the TV-only layout; the shared built-in display default stays
at 120 Hz. The separate Windows cursor helper lives in `moonlight/windows/`.
No pairing certificates, passwords, or SSH private keys are included.
