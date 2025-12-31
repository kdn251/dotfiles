#
# ~/.zshrc
#

# --- SECRETS MANAGEMENT ---
# Loads private credentials and variables from a local file that is NOT
# committed to version control.
if [ -f "$HOME/.config/zsh/secrets.zsh" ]; then
    source "$HOME/.config/zsh/secrets.zsh"
fi
# --------------------------

# Initialize completions FIRST
autoload -Uz compinit && compinit

# Enable prompt substitution
setopt PROMPT_SUBST

# Consistent color definitions
autoload -U colors && colors

# Aliases
alias ls='ls --color=auto'
alias grep='grep --color=auto'
alias vim="nvim"
alias wifi="nmtui"
alias pip-toggle="HYPRLAND_INSTANCE_SIGNATURE=dummy ./pip-toggle.sh"
alias php='php-legacy'
alias fixplanewifi='sudo resolvectl dns wlan0 8.8.8.8 1.1.1.1 && sudo nmcli general reload && sudo systemctl restart NetworkManager'
alias newsboat='newsboat && ~/scripts/update-live-list.sh &'

# Git branch function (simplified)
parse_git_branch() {
  git branch 2> /dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/(\1)/'
}

dlyt() {
    yt-dlp -f "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[ext=mp4]/best" --merge-output-format mp4 "$1"
}

# Cleaner prompt using consistent zsh color codes
PS1='%F{green}%n%f%F{yellow}@%m%f %F{213}%1~%f %F{yellow}$(parse_git_branch)%f '

# Autosuggestions
source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh

# Better word deletion
autoload -U select-word-style
select-word-style bash

# Autosuggestions configuration
ZSH_AUTOSUGGEST_MIN_LENGTH=3
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=240'
ZSH_AUTOSUGGEST_STRATEGY=(history completion)
ZSH_AUTOSUGGEST_BUFFER_MAX_SIZE=20
ZSH_AUTOSUGGEST_USE_ASYNC=true

# Basic completion options
setopt AUTO_LIST
setopt AUTO_MENU
setopt COMPLETE_IN_WORD

# PATH and environment
export PATH="$HOME/.phpenv/bin:$PATH"
export PATH="$HOME/scripts:$PATH"
eval "$(phpenv init -)"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

export PATH=/home/knaught/.opencode/bin:$PATH
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk
export ANDROID_HOME=/opt/android-sdk
export PATH=$PATH:$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools

# Dart completion
[[ -f /home/knaught/.dart-cli-completion/zsh-config.zsh ]] && . /home/knaught/.dart-cli-completion/zsh-config.zsh || true
export EDITOR=nvim
