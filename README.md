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

