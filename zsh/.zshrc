# --- SECRETS MANAGEMENT ---
if [ -f "$HOME/.config/zsh/secrets.zsh" ]; then
    source "$HOME/.config/zsh/secrets.zsh"
fi

# --- 1. OPTIMIZED COMPLETIONS (The Cache Fix) ---
# Only run compinit if the cache is older than 24 hours
autoload -Uz compinit
if [[ -n ${ZDOTDIR:-$HOME}/.zcompdump(#qN.mh+24) ]]; then
    compinit
else
    compinit -C # Use the cache (-C) for speed
fi

# --- 2. ENVIRONMENT & PATH ---
export PATH="$HOME/.phpenv/bin:$HOME/scripts:/home/knaught/.opencode/bin:$PATH"
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk
export ANDROID_HOME=/opt/android-sdk
export PATH=$PATH:$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools
export EDITOR=nvim

# --- 3. LAZY LOADING (The Big Performance Gain) ---

# LAZY PHPENV: Only init when first called
phpenv() {
    unfunction phpenv
    eval "$(command phpenv init -)"
    phpenv "$@"
}

# LAZY NVM: This is your 1-second fix. 
# It won't load NVM until you actually type 'nvm', 'node', or 'npm'.
export NVM_DIR="$HOME/.nvm"
nvm() {
    unfunction nvm node npm
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    nvm "$@"
}
node() { nvm >/dev/null; node "$@" }
npm() { nvm >/dev/null; npm "$@" }

# --- 4. ALIASES & FUNCTIONS ---
alias ls='eza --icons' # Use eza since we're optimizing
alias grep='rg'        # Use ripgrep
alias vim="nvim"
alias wifi="nmtui"
alias newsboat='newsboat && ~/scripts/update-live-list.sh &'
alias gstart='systemctl --user start rclone-gdrive.service'
alias gstop='systemctl --user stop rclone-gdrive.service'

# Fast Git Branch check (no subshells/sed for speed)
parse_git_branch() {
    local branch=$(git branch --show-current 2>/dev/null)
    [[ -n $branch ]] && echo "($branch)"
}

# --- 5. LOOK AND FEEL ---
setopt PROMPT_SUBST
autoload -U colors && colors
PS1='%F{green}%n%f%F{yellow}@%m%f %F{213}%1~%f %F{yellow}$(parse_git_branch)%f '

# Use zsh-defer for non-critical plugins if you have the package
if [ -f /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]; then
    source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
fi

# Autosuggestions configuration
ZSH_AUTOSUGGEST_USE_ASYNC=true
ZSH_AUTOSUGGEST_STRATEGY=(history completion)

# Basic options
setopt AUTO_LIST AUTO_MENU COMPLETE_IN_WORD
autoload -U select-word-style && select-word-style bash

# Dart completion
[[ -f /home/knaught/.dart-cli-completion/zsh-config.zsh ]] && . /home/knaught/.dart-cli-completion/zsh-config.zsh
