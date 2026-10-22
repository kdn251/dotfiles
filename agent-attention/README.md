# Agent Attention

Pauses a foreground Moonlight stream when a local agent needs attention, verifies
the pause screen, shows an eight-second notification, and focuses the agent window.
Runs entirely on the Linux client; no gaming-PC installation is required.

## Restore on Arch / Hyprland

From a checkout of this repository, inside your logged-in graphical session:

```sh
sudo pacman -S --needed python python-pillow python-websocket-client grim wtype libnotify
python3 ~/dotfiles/agent-attention/.local/share/agent-attention/install.py
```

The installer links this Stow-compatible package into your home directory, merges
only its own Claude Code hooks, and enables the systemd user service. Existing
files are backed up under `~/.local/state/agent-attention/backups/`. Different
existing game profiles are preserved. It is safe to rerun. A normal `stow
agent-attention` restores files, but still run the installer for Claude hooks and
service activation. Codex and Claude Code must be installed and authenticated
separately. No credentials, chat histories, logs, or full game screenshots are tracked.

The installed Codex runtime must expose the shared local app-server socket.
The observer reads thread metadata every two seconds to detect completion,
approval requests, questions, and session errors; it never answers or approves them.
It does not cover browser chats or standalone Codex app-server instances.
Claude Code hooks cover Stop, PermissionRequest, selected Notification events,
AskUserQuestion, and Elicitation. Start a fresh Claude session after restoring.

## Claude in Herdr over SSH

`herdr_remotes` in the profile config enables an observer for SSH alias `boole`.
It launches a small transient Python helper through authenticated, non-interactive
SSH and reads Herdr's public `agent.list` API every two seconds. No remote files,
hooks, credentials, or open network listeners are installed. The helper exits
when its SSH connection closes. Existing SSH forwards are disabled for this
connection. Python 3 and a running, compatible Herdr server are required remotely.

A completion or blocked status must remain stable for two samples before alerting.
New sessions and reconnects establish a baseline rather than replay old work.
The observer reports only Claude; the separate Pi popup integration is unchanged.
Herdr's Claude status is screen-detected, so detection accuracy depends on Herdr.

Routing finds the unique local `herdr --remote boole` process and its Kitty window.
After pausing, it verifies the remote pane, terminal, and Claude session identities,
uses `agent.focus` to select that exact remote pane/tab, then focuses the local
window. Public focus commands can update other clients attached to the same Herdr
session too. Multiple matching local Herdr clients are ambiguous and result in a
notification only. Saved-machine UI connections without `--remote` are not covered.

On a new machine, configure SSH access to boole first, or set the endpoint's
`enabled` to false. Each endpoint has `host`, `remote_socket`, and `enabled`.
Restart the service after changing remote endpoints. Verified end to end on October 22, 2026: the user confirmed that a real Claude
completion inside Herdr on boole paused Moonlight, displayed the notification,
and selected the correct remote Claude tab. Local Claude and local Codex
completion + pause + focus were also verified.

## Standalone Claude or Codex over plain SSH

`ssh_remotes` enables standalone sessions on SSH alias `boole`. Use an ordinary
interactive `ssh boole` connection and start a fresh `claude` or `codex` process.
The local observer matches the remote `SSH_CONNECTION` TCP tuple to the local
SSH process and Kitty window/tab. It never guesses from window titles. SSH
ControlMaster multiplexing, tmux/screen, jump hosts/NAT that change the observed
connection tuple, and other ambiguous routes are not supported for automatic
focus. Herdr sessions are excluded here and keep their separate integration.

On boole, Codex is installed as the yay-managed `openai-codex-bin` package.
The remote installer adds a guarded Bash alias: plain `codex` automatically uses
`--no-daemon` in standalone interactive SSH sessions when the CLI supports it.
The shared daemon retains its original SSH environment after reconnecting, which
otherwise makes completion events point at an expired connection. Session-local
mode keeps the backend with this terminal; it does not provide shared-daemon
background persistence after the terminal closes. Herdr, tmux/screen, non-SSH
shells, and older CLIs are excluded. Existing shells need to reconnect or source
`~/.local/share/agent-attention-ssh/codex-ssh.bash` once before restarting Codex.

The remote sender is a small Python standard-library script. Claude hooks cover
completion, permission requests, questions, and selected attention notifications.
Codex's documented `notify` callback covers `agent-turn-complete` only; standalone
Codex approval prompts are **not** covered by this older CLI integration. No
agent upgrades or permission-setting changes are made. Fresh agent sessions load
the callbacks; an existing session may not reload them.

To restore the remote sender after installing the local package:

```sh
ssh -o ClearAllForwardings=yes boole 'mkdir -p ~/.local/share/agent-attention-ssh'
scp -o ClearAllForwardings=yes \
  ~/dotfiles/agent-attention/.local/share/agent-attention/{ssh_remote,install_ssh_remote}.py \
  boole:.local/share/agent-attention-ssh/
ssh -o ClearAllForwardings=yes boole \
  'python3 ~/.local/share/agent-attention-ssh/install_ssh_remote.py'
systemctl --user restart agent-attention
```

The remote installer backs up settings, preserves existing Herdr hooks and other
Claude preferences, and refuses to overwrite an unrelated Codex notify command.
No remote service or listening network port is added. Small private event files
contain only source, reason, session ID, project basename, and SSH routing metadata;
conversation text and tool arguments are discarded. Files older than a day are
pruned on subsequent events. The local observer streams new events over an
independent authenticated SSH connection; reconnects never replay a backlog.

To disable this flow, set its `ssh_remotes` entry's `enabled` to false and restart
the local service. To remove remote callbacks, remove only handlers containing
`agent-attention-ssh/ssh_remote.py` from Claude settings and that sender's root
`notify` entry from Codex config and the source line for `codex-ssh.bash` in
`~/.bashrc`, then remove `~/.local/share/agent-attention-ssh`.
Do not overwrite other agent settings with an old backup.

Verification: automated behavior/restore tests pass. A live temporary interactive
SSH session emitted a transport probe, and the local service resolved the exact
Kitty window and PTY among the other SSH connections. This probe does not pause
or change focus. A real standalone Claude completion paused the game; its first
focus attempt was blocked by a windowed-menu detection mismatch. The detector now
searches a small position/scale range for Resume, with the captured frame covered
by a regression test. Focus-only verification selected the correct standalone
Claude terminal. A full completion retest and standalone Codex test remain.

## Controls and profiles

```sh
agent-attention status
agent-attention disable
agent-attention enable
agent-attention game expedition-33
agent-attention mode auto-expedition33
systemctl --user status agent-attention
journalctl --user -u agent-attention -n 30
```

`~/.config/agent-attention/config.json` reloads on each event. Add games under
`games`, then select the appropriate profile before changing games: Moonlight's
host title doesn't reveal the running game. The initial profile is Expedition 33.
A profile has a `mode` and a `modes` mapping. Each mode supports `key` (XKB name),
`enabled`, `settle_ms`, optional `modifiers`, optional `hold_ms` (no modifiers),
and an optional detector. Without a detector only input delivery is confirmed.

Verified on October 22, 2026:

| Context | Pause input | Visual verification |
|---|---|---|
| Expedition 33 cutscene | F | Centered Pause label |
| Expedition 33 battle | Escape held 150 ms via wtype | Resume menu label |
| Expedition 33 exploration | Escape held 150 ms via wtype | Resume menu label |

Instant Hyprland Escape shortcuts did not reliably open the menu. F selects an
attack during battle, so it must stay cutscene-only. Already-paused screens are
recognized before sending a key, avoiding an accidental resume. Failure to verify
pause means a notification without switching. The service never selects menu
items or confirms quitting. Duplicate alerts and closely spaced interruptions
are suppressed; other desktop work never loses focus automatically.

**On a new machine, disable the service's actions while checking the display:**
`agent-attention disable`. The visual templates and cinematic letterbox heuristic
were verified on the current 3:2 display, English UI, and fullscreen/windowed
Moonlight sizes. Another aspect ratio, language, stream layout, or font may need
recalibration of `screen`, `cinematic`, and the template crops. Re-enable after a
live test. These are visual heuristics, not the game's internal pause state.

Codex focus uses a unique conversation name in the visible window title. Hidden
terminal tabs or ambiguous titles receive notifications without automatic focus.
Claude uses process ancestry and Kitty window IDs to focus the correct tab/split;
this needs Kitty's existing `allow_remote_control yes` setting. No unknown window
is guessed. The Codex logo is an app asset copied from the installed Codex bundle.

## Validation and maintenance

```sh
python3 -m unittest discover -s ~/dotfiles/agent-attention/.local/share/agent-attention -p 'test_*.py'
python3 ~/dotfiles/tests/check-agent-attention-install.py
```

`agent-attention test` runs the full sequence for the invoking terminal, labeled
Test. Real Codex events include its logo. It is not merely a notification preview.
Code changes require `systemctl --user restart agent-attention`; profile changes
reload automatically. Logs rotate in `~/.local/state/agent-attention/events.log`.
Profile edits through the CLI preserve the link to this repository. Commit and
push subsequent profile changes to retain them across machines.

To remove: disable the service with `systemctl --user disable --now
agent-attention`, remove only hook handlers containing `agent-attention` from
Claude settings, and unstow/remove the package links. Do not blindly restore an
old Claude settings backup over newer preferences.
