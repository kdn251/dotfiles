#!/bin/bash
input=$(cat)

# 1. Debug log (keep this for now)
# echo "$(date): Attempting to copy: ${input:0:10}..." >>~/tmux_debug.log

# 2. Base64 encode the content
content=$(echo "$input" | base64 | tr -d '\n')

# 3. The "Secret Sauce": Find the actual TTY of the active tmux pane
# This ensures the escape sequence hits the SSH tunnel correctly.
TTY=$(tmux display-message -p '#{pane_tty}')

# 4. Send the escape sequence directly to that TTY
printf "\033Ptmux;\033\033]52;c;${content}\a\033\\" >"$TTY"
