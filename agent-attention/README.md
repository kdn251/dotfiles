# Agent Attention

Pauses a foreground Moonlight stream when a local agent needs attention, verifies
the pause screen, shows an eight-second notification, and focuses the agent window.
Runs entirely on the Linux client; no gaming-PC installation is required.

## Restore on Arch / Hyprland

From a checkout of this repository, inside your logged-in graphical session:

```sh
sudo pacman -S --needed python python-pillow python-websocket-client python-gobject python-cairo gtk3 gtk-layer-shell grim wtype libnotify waybar stow
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

Kevin's persistent Codex defaults on boole are `approval_policy = "never"` and
`sandbox_mode = "danger-full-access"`. The restore command below explicitly
recreates these defaults; omit `--codex-full-access` to preserve another machine's
permission settings. Install Codex with `yay -S openai-codex-bin` on a fresh Arch
host and verify `type -a codex` in an interactive shell has no npm/fnm shadow copy.

The remote sender is a small Python standard-library script. Claude hooks cover
completion, permission requests, questions, and selected attention notifications.
Codex's documented `notify` callback covers `agent-turn-complete` only; standalone
callbacks are filtered against the local session record to require a completed
user turn. Internal threads, subagents, progress messages, and active turns do
not trigger the interruption. Only lifecycle metadata is used, never message text.
Missing or unrecognized session records suppress the callback rather than guess.
Standalone
Codex approval prompts are **not** covered by this older CLI integration. No
agent upgrades are made by the sender installer. Fresh agent sessions load
the callbacks; an existing session may not reload them.

To restore the remote sender after installing the local package:

```sh
ssh -o ClearAllForwardings=yes boole 'mkdir -p ~/.local/share/agent-attention-ssh'
scp -o ClearAllForwardings=yes \
  ~/dotfiles/agent-attention/.local/share/agent-attention/{ssh_remote,activity_probe,install_ssh_remote}.py \
  boole:.local/share/agent-attention-ssh/
ssh -o ClearAllForwardings=yes boole \
  'python3 ~/.local/share/agent-attention-ssh/install_ssh_remote.py --codex-full-access'
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
Claude terminal. Kevin confirmed the full standalone Claude and Codex flows work
on 2026-10-22 after the menu, internal-thread filtering, and persistent permission
fixes. No further live retest is pending for these flows.

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
| Expedition 33 party menu | No input; already in menu | Journal and Inventory labels together |

On October 23 the party menu was added after real attention events failed the
Resume-only detector. Both labels must match before switching without input.
Live party-menu attention successfully selected the remote Claude tab without
closing the menu. Nested character/Pictos menus are not yet recognized by this
check; those need separate reference captures. Existing display/language limits
below also apply to the party-menu templates.

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

## Live Sisyphus activity indicator

Waybar's first right-side module is `custom/agent_sisyphus`. It consumes the
attention service's private `~/.local/state/agent-attention/activity.json` snapshot.
Calcifer and the preview selector are not enabled in the bar.

- Pushing with a count: at least one monitored agent has an active turn.
- Raised hand and `!`: an agent is waiting for attention. If others are still
  working, the pushing animation remains and the count also gets an `!`.
- Dim, stationary sprite and `?`: a monitor is stale or a session is unclassified.
- Seated Sisyphus with a green check on the boulder: a verified completion, shown for six seconds.
  If other agents are working, the count gets a brief dot instead.
- Dim resting sprite: all monitored sessions are idle; it remains clickable.
  The bar keeps a fixed 32px height.

The tooltip identifies hosts and agent types, waiting states, unavailable
monitors, and last lifecycle activity where available. Active does not prove
useful progress: long commands or stalled requests can remain active. No CPU
heuristic or arbitrary timeout pretends that a task completed.

Local Codex uses its read-only status API, supplemented by lifecycle records for
other local Codex backends. Live Codex backends on boole are discovered by their
open rollout descriptors; only user-thread lifecycle metadata is exported.
Closed processes and internal/subagent threads are excluded. Claude uses
UserPromptSubmit/tool/permission/stop/session-end hooks tied to a live process
identity, while remote Herdr supplies its pane states. Start fresh standalone
Claude sessions after installing the hooks. An older open Claude session without
hook state is unknown until it supplies a lifecycle event.

The existing SSH stream carries the boole snapshot; there is no new network port
or remote service. Missing heartbeat data expires after eight seconds, and stale
Waybar snapshots cannot animate as working. This display does not send inputs,
approve commands, or change the existing pause-and-focus behavior.

Restore the `waybar` Stow package as well as `agent-attention`, run the local
installer and the remote restore commands above, then restart both user services:
`systemctl --user restart agent-attention waybar`.

Click Sisyphus for a compact chat list: animated harness icon and task/chat name.
Working rows animate; inactive rows are dimmed. Hover a long title to scroll it. Click a row to focus that exact session where routing is available.
Hover the logo for Codex/Claude, reported model, host, and background-job details. Unknown
models are explicitly labeled, never inferred from a preferred/default model.
Idle sessions with no matching tab are omitted; active background jobs remain
visible with disabled navigation. Close with Escape or a click outside the popup. The popup uses Python GObject, GTK 3 and GtkLayerShell.

Navigation re-reads the live snapshot and revalidates process start times, SSH
connections, and Herdr pane/session IDs at click time. If Moonlight is active,
it confirms the configured pause before focusing the selected terminal. Missing
or ambiguous tabs fail visibly instead of selecting another conversation.

Quiet long-running work is not flagged amber. Only missing/unknown monitoring
does that; an explicit waiting-for-input state has its separate attention marker.
Completion uses lifecycle markers with a startup baseline, so opening/restarting
the monitor does not celebrate old tasks. To preview the completion pose for
15 seconds without changing any real status, run:
`python3 ~/.config/waybar/scripts/agent-status.py --preview-complete`.

The compact agent popup sits 4px below Waybar, uses the same slate/teal palette as
the other status popups, and closes on an outside click or Escape. Rows show animated logos while working and still logos otherwise; hover for the
exact status. The Claude logo SVG comes from Simple Icons (CC0):
https://github.com/simple-icons/simple-icons/blob/develop/icons/claude.svg

Working Codex rows loop the user's `codex-animated.mp4` asset (3 seconds, 90 frames),
using a 48px transparent frame strip. Working Claude rows loop an existing Claude thinking GIF, preserving its timing at 30 fps. Idle, waiting, and unknown rows keep still logos. The GTK frame clock
runs only while the popup is visible. Rebuild the strip with
`python3 ~/.local/share/agent-attention/build-codex-frames.py` (requires FFmpeg/Pillow).
Source: https://drive.google.com/file/d/1KusszYKkyRO_Cs-zIeihihe2_w19BE67/view

Claude thinking animation source (uploaded by adithya1):
https://tenor.com/view/claude-claude-code-thinking-gif-6554436885102008506
Original GIF retained as `claude-thinking.gif`; rebuild the transparent frame strip
with `build-claude-frames.py` (Pillow). It expands and contracts the orange star.
This is a community-uploaded asset, not a verified official Anthropic download.
Status circles are omitted. The idle Claude logo uses the animation’s orange (#d97757).

Agent attention notifications, pausing, and automatic focus occur only while a
Moonlight stream is focused. Other desktop apps and the Moonlight launcher stay
silent; Herder audio and Waybar monitoring are unchanged. Long chat titles scroll
on row hover and reset on pointer exit; hover the logo for session details.

The repository includes original animation assets and pre-rendered frame strips;
new machines do not need Drive access, FFmpeg, or Lottie rendering dependencies
for normal use. Install the packages above, restore the `waybar` Stow package,
and run the installer. Game pause detection still needs a check on a new display.
