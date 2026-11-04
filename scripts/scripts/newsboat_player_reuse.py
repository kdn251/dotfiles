"""Open local Newsboat media in a compatible, already running player."""
import json
import os
from pathlib import Path
import uuid
import subprocess
import sys
from mpv_clip import Player


def reuse(url, title='', endpoint='/tmp/mpv-yt-ipc'):
    # Random-pick playback has a separate close/unstar lifecycle.
    if os.environ.get('NEWSBOAT_RANDOM_LIFECYCLE') or not Path(endpoint).exists():
        return False
    player = None
    submitted = False
    try:
        player = Player(endpoint)
        player.socket.settimeout(.5)
        capability = player.get('user-data/newsboat/reusable')
        if not isinstance(capability, dict) or capability.get('version') != 1:
            return False
        if capability.get('random') or capability.get('context', '') != os.environ.get('NEWSBOAT_PLAYLIST_CONTEXT', ''):
            return False
        from newsboat_media import playback_file, cached_title
        local = playback_file(url)
        if not local:
            return False
        from newsboat_autoplay import plan
        target = dict(url=url, path=str(local), title=title or cached_title(url),
                      local=True, plan=plan(url), request=uuid.uuid4().hex)
        player.command('script-message-to', 'newsboat_playlist_playback', 'open-local', json.dumps(target))
        submitted = True
        # Reopening in an existing window must restore the same pinned default
        # as a fresh player, without moving a window the user positioned.
        pid = player.get('pid')
        if isinstance(pid, int) and pid > 0:
            subprocess.Popen([sys.executable, str(Path(__file__).with_name('media_chat_fullscreen.py')),
                              'pin', str(pid)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        # Once delivered, never kill the player just because a slow disk takes
        # longer to decode. Its normal error handling owns this request.
        return True
    except (OSError, ValueError):
        return submitted
    finally:
        if player is not None:
            player.close()
