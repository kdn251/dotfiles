# GeForce NOW interface scaling

The GeForce NOW application-menu entry uses `.local/bin/geforcenow-scaled`
to set the native Flatpak client's CEF interface zoom to 200% before launch.
It preserves other preferences and skips edits while the app is running.
Display resolution and streaming settings are not changed.

Requires Python 3 and the `com.nvidia.geforcenow` Flatpak. Install this package
with `stow --no-folding -t "$HOME" desktop-files` from the dotfiles repository.
If NVIDIA has already created `~/.local/share/applications/com.nvidia.geforcenow.desktop`,
back up that file before stowing. Keep the separate `NVIDIA GeForce NOW` vendor
launcher in that directory; the wrapper uses it for update/relaunch handling.

Launch GeForce NOW from the application menu to apply the saved zoom. Direct
`flatpak run` calls bypass the wrapper. If an installer replaces the desktop
entry, restore the Stow link. No private profile data is stored in this repository.
