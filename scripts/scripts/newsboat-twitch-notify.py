#!/usr/bin/env python3
"""Twitch playback notification: creator portrait plus a Twitch app badge."""
import json
from pathlib import Path
import re
import subprocess
import sys
from newsboat_media import identity, records


def notify(url, path, title, metadata):
    metadata = {k.lower(): v for k, v in metadata.items()} if isinstance(metadata, dict) else {}
    creator = metadata.get('uploader') or metadata.get('artist') or ''
    login = metadata.get('uploader_id') or creator
    icon = ''
    for _, job in records():
        if identity(job['url']) == identity(url):
            title = job.get('title') or title
            creator = job.get('creator') or creator
            icon = job.get('icon') or ''
            break
    # Older automatically downloaded VODs store the creator and title in the name.
    local = Path(path)
    if local.is_file():
        match = re.fullmatch(r'([A-Za-z0-9_]+) - (.+) - [0-9]+', local.stem)
        if match:
            login = match[1]
            creator = creator or login
            title = match[2]
    login = login or creator
    if not icon and re.fullmatch(r'[A-Za-z0-9_]+', login):
        try:
            result = subprocess.run([str(Path(__file__).with_name('twitch-profile-pic.sh')), login],
                                    capture_output=True, text=True, timeout=15)
            icon = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    badge = Path('/usr/share/icons/Papirus/48x48/apps/gnome-twitch.svg')
    args = ['notify-send', '-a', 'Twitch', '--app-icon', str(badge) if badge.exists() else 'twitch',
            '-t', '5000', '-u', 'low']
    if icon and Path(icon).is_file():
        args += ['-h', 'string:image-path:' + icon]
    subprocess.run(args + ['--', title or 'Twitch VOD', creator or 'Twitch'], check=False)


if __name__ == '__main__':
    notify(*sys.argv[1:4], json.loads(sys.argv[4]))
