"""Session-scoped recovery of files removed by a visual bulk action."""
import hashlib
import json
import os
from pathlib import Path
import shutil


def session_directory():
    import newsboat_media as media
    journal = os.environ.get('NEWSBOAT_UNDO_FILE')
    if not journal:
        raise ValueError('Restart Newsboat before using undoable bulk deletion')
    session = hashlib.sha256(journal.encode()).hexdigest()
    # Keep large videos on disk, outside the scanned library and /tmp (tmpfs).
    return media.ROOT.parent/'.newsboat-deleted'/session


def directory(token):
    return session_directory()/hashlib.sha256(token.encode()).hexdigest()


def preserve(url, paths, jobs, archive_lines, token):
    import newsboat_media as media
    folder = directory(token)
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    files = []
    for path in paths:
        for candidate in (path, path.with_suffix('.meta'), path.with_suffix('.info.json')):
            if candidate.is_file() and media.inside(candidate) and str(candidate) not in files:
                files.append(str(candidate))
    manifest = dict(url=url, files=files, jobs=[(str(p), job) for p,job in jobs], archive=archive_lines)
    media.atomic_write(folder/'manifest.json', json.dumps(manifest))
    try:
        for index, path in enumerate(files):
            shutil.move(path, folder/str(index))
    except OSError:
        for index, path in enumerate(files):
            if (folder/str(index)).exists():
                shutil.move(folder/str(index), path)
        shutil.rmtree(folder)
        raise


def restore(url, token):
    import newsboat_media as media
    with media.library_lock():
        folder = directory(token)
        # The native checkpoint precedes deletion. A rejected action (e.g. an
        # active download) creates no recovery folder and changed nothing.
        if not folder.exists():
            return
        manifest = json.loads((folder/'manifest.json').read_text())
        if manifest['url'] != url:
            raise ValueError('Undo URL does not match deleted download')
        for index, name in enumerate(manifest['files']):
            path = Path(name)
            if not media.inside(path) or path.exists():
                raise ValueError('Cannot restore over an existing download')
            if not (folder/str(index)).is_file():
                raise ValueError('Deleted file is no longer available')
        moved = []
        try:
            for index, name in enumerate(manifest['files']):
                path = Path(name);path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(folder/str(index), path)
                moved.append((index, path))
        except OSError:
            for index,path in reversed(moved):shutil.move(path,folder/str(index))
            raise
        for name, job in manifest['jobs']:
            path = Path(name)
            if path.parent != media.STATE or path.is_symlink():
                raise ValueError('Invalid download record')
            media.atomic_write(path, json.dumps(job))
        archive = media.ROOT/'.downloaded-twitch-vods'
        if manifest['archive']:
            lines = archive.read_text().splitlines() if archive.exists() else []
            lines += [line for line in manifest['archive'] if line not in lines]
            media.atomic_write(archive, '\n'.join(lines)+'\n')
        media.rebuild_unlocked()
        shutil.rmtree(folder)


def cleanup():
    folder = session_directory()
    if folder.exists():shutil.rmtree(folder)
