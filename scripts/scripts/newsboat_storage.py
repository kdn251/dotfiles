"""Cached sizes of completed Downloads and Playthroughs for list titles."""
import json
from pathlib import Path
import newsboat_media as media


def readable(size):
    value = float(size)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{int(value)} B' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


def publish(state):
    state = Path(state)
    members = set()
    for path in (state.parent/'youtube-playlists/playthroughs').glob('*.json'):
        try:
            group = json.loads(path.read_text())
            urls = group.get('selected_urls', [row['url'] for row in group.get('rows', [])])
            members.update(media.identity(url) for url in urls)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    files = {}
    try:
        for path, entry in json.loads((state/'.media-index.json').read_text()).items():
            if entry.get('valid'):
                files[Path(path)] = media.filename_identity(Path(path))
    except (OSError, ValueError):
        pass
    for path in state.glob('*.json'):
        try:
            job = json.loads(path.read_text())
            if job.get('status') == 'done':
                for file in job.get('files', []):
                    files[Path(file)] = media.library_identity(job['url'])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    totals = {'downloads': 0, 'playthroughs': 0}
    seen = set()
    for path, key in files.items():
        try:
            path = path.resolve()
            if not key or path.is_relative_to(media.CACHE.resolve()) or path.parent == (media.ROOT/'twitch-vods').resolve():
                continue
            stat = path.stat()
            inode = (stat.st_dev, stat.st_ino)
            if not path.is_file() or inode in seen:
                continue
            seen.add(inode)
            totals['playthroughs' if key in members else 'downloads'] += stat.st_size
        except OSError:
            continue
    target = state.parent/'starred-urls.txt.storage'
    content = ''.join(f'{kind}\t{readable(size)}\n' for kind, size in totals.items())
    if not target.exists() or target.read_text() != content:
        media.atomic_write(target, content)
    return totals
