#!/usr/bin/env python3
"""Run the installed yt-dlp zipapp from a versioned, bytecode-friendly cache."""
import hashlib
import os
from pathlib import Path
import shutil
import sys


def runtime(source, cache):
    source=Path(source).resolve()
    stat=source.stat()
    signature=hashlib.sha256(f'{source}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}:{sys.implementation.cache_tag}'.encode()).hexdigest()[:24]
    target=Path(cache)/signature
    entry=target/'__main__.py'
    if (target/'.complete').is_file() and entry.is_file():
        return entry
    import fcntl
    import tempfile
    import zipfile
    if not zipfile.is_zipfile(source):
        return source  # System packages/native executables already avoid zip imports.
    target.parent.mkdir(parents=True,exist_ok=True)
    with (target.parent/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (target/'.complete').is_file() and entry.is_file():
            return entry
        with zipfile.ZipFile(source) as archive:
            if '__main__.py' not in archive.namelist() or 'yt_dlp/__init__.py' not in archive.namelist():
                return source
            with tempfile.TemporaryDirectory(prefix='.unpack-',dir=target.parent) as directory:
                staging=Path(directory)/'runtime';staging.mkdir()
                for info in archive.infolist():
                    if not (staging/info.filename).resolve().is_relative_to(staging.resolve()):
                        raise ValueError('Invalid runtime archive path')
                archive.extractall(staging)
                (staging/'.complete').touch()
                if target.exists():shutil.rmtree(target)
                staging.rename(target)
    return entry


def main():
    source=os.environ.get('NEWSBOAT_YTDL_SOURCE') or str(Path.home()/'.local/bin/yt-dlp')
    if not Path(source).is_file():source=shutil.which('yt-dlp') or source
    cache=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'newsboat-yt-dlp-runtime'
    try:entry=runtime(source,cache)
    except (OSError,ValueError):entry=Path(source)
    if sys.argv[1:]==['--prepare-runtime']:
        print(entry)
        return
    # Keep arguments, extraction behavior and selected formats unchanged.
    if entry==Path(source).resolve() or entry==Path(source):
        os.execv(source,[source,*sys.argv[1:]])
    os.execv(sys.executable,[sys.executable,str(entry),*sys.argv[1:]])


if __name__=='__main__':main()
