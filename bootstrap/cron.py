#!/usr/bin/env python3
"""Merge desktop jobs without enabling the source machine's automatic Git pushes."""
from pathlib import Path
import os
import subprocess
import tempfile

START = '# BEGIN dotfiles desktop jobs'
END = '# END dotfiles desktop jobs'


def merge(existing, template, home, uid):
    if existing.count(START) != existing.count(END) or existing.count(START) > 1:
        raise ValueError('Malformed dotfiles cron block; reconcile the crontab first')
    if START in existing:
        before, rest = existing.split(START, 1)
        _, after = rest.split(END, 1)
        existing = before + after.lstrip('\n')
    jobs = []
    for line in template.splitlines():
        if not line or line.startswith('#') or '=' in line.split()[0]:
            continue
        if 'backup-packages.sh' in line or 'update-packages.sh' in line:
            continue
        # Use per-job env assignments so unrelated cron jobs are unaffected.
        fields = line.split(maxsplit=5)
        command = fields[5].replace('/home/knaught', home).replace('/run/user/1000', f'/run/user/{uid}')
        if any(command in old for old in existing.splitlines() if not old.startswith('#')):
            continue
        env = f'PATH={home}/.local/bin:/usr/local/bin:/usr/bin:/bin XDG_RUNTIME_DIR=/run/user/{uid} DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus'
        jobs.append(' '.join(fields[:5]) + ' ' + env + ' ' + command)
    return existing.rstrip() + '\n' + START + '\n' + '\n'.join(jobs) + '\n' + END + '\n'


def main():
    result = subprocess.run(['crontab', '-l'], text=True, capture_output=True)
    if result.returncode and 'no crontab for' not in result.stderr:
        raise RuntimeError(result.stderr)
    original = result.stdout
    home = Path.home()
    if original:
        backup = home / '.local/state/dotfiles'
        backup.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode='w', prefix='crontab-', dir=backup, delete=False) as out:
            out.write(original)
    template = (Path(__file__).resolve().parents[1] / 'crontab_knaught').read_text()
    subprocess.run(['crontab', '-'], input=merge(original, template, str(home), os.getuid()), text=True, check=True)


if __name__ == '__main__':
    main()
