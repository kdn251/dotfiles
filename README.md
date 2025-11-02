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
3. Run `pacman -Qqe | grep -v "$(pacman -Qqm)" > pacman-packages.txt` to update list of pacman installed packages
4. Run `pacman -Qqm > aur-packages.txt` to update list of AUR installed packages
5. Run `crontab -l > ~/dotfiles/crontab_knaught` to get up to date crontab file to push to repo and pull down on other machines. On other machines run `crontab ~/dotfiles/crontab_knaught` (or wherever the file lives) to recreate the cron jobs on the new machine
6. Copy my `~/.zshrc` file from another machine directly/safely since it has credentials in it
7. Start all necessary services I rely on with `sudo systemctl starts SERVICE_NAME` (still need to gather this list of services and place them in a script to start the all)
8. Probably need to run `sudo stow -t / root-etc` to stow files in `/etc` correctly (maybe can add this to startup script as well)
