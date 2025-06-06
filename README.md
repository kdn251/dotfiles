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
