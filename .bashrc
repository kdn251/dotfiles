#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

# Variables 
GREEN=$(tput setaf 2)
YELLOW=$(tput setaf 3)

# Aliases
alias ls='ls --color=auto'
alias grep='grep --color=auto'
alias vim="nvim"
alias wifi="nmtui"

# Git branch in prompt
parse_git_branch() {
  git branch 2> /dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/(\1)/'
}

# PS1='${GREEN}\u${YELLOW}@\h \[\033[38;5;213m\]\W\[\033[0m\]\$ '
PS1='${GREEN}\u${YELLOW}@\h \[\033[38;5;213m\]\W\[\033[33m\] $(parse_git_branch)\[\033[0m\]\$ '
# PS1='\u@\h \W\$ '

alias pip-toggle="HYPRLAND_INSTANCE_SIGNATURE=dummy ./pip-toggle.sh"
export PATH="$HOME/.phpenv/bin:$PATH"
eval "$(phpenv init -)"
