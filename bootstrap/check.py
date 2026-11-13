#!/usr/bin/env python3
"""Read-only restore audit. Names/status only: never prints credentials or config contents."""
from pathlib import Path
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]


def lines(path):
    return [s.strip() for s in path.read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]


def run(*args):
    return subprocess.run(args, text=True, capture_output=True)


def main():
    problems = []
    def check(ok, label):
        print(('OK   ' if ok else 'TODO ') + label)
        if not ok:
            problems.append(label)
    check(Path.home() == Path('/home/knaught') and ROOT == Path.home() / 'dotfiles', 'supported account and checkout location')
    if shutil.which('pacman'):
        installed = set(run('pacman', '-Qq').stdout.splitlines())
        wanted = set(lines(ROOT/'pacman-packages.txt') + lines(ROOT/'aur-packages.txt') + lines(ROOT/'bootstrap/packages.txt'))
        missing = sorted(p for p in wanted - installed if not p.endswith('-debug'))
        check(not missing, 'packages installed' + (': missing ' + ', '.join(missing) if missing else ''))
    else:
        check(False, 'pacman available (Arch Linux required)')
    if shutil.which('stow'):
        result = run('stow', '--simulate', '--no-folding', '-d', str(ROOT), '-t', str(Path.home()), *['--ignore=' + s for s in lines(ROOT/'bootstrap/stow-ignore.txt')], *lines(ROOT/'bootstrap/stow-packages.txt'))
        check(result.returncode == 0, 'Stow has no conflicts (simulation only; does not prove links already exist)')
        if result.returncode:
            print(result.stderr)
    else:
        check(False, 'GNU Stow available')
    for rel in ['.local/libexec/waybar-hypr57', '.local/lib/newsboat-paged/newsboat',
                '.local/share/newsboat/article-venv/bin/python', '.local/share/mpv/fonts/AppleColorEmoji.ttf',
                'scripts/obs-display-create.so']:
        check((Path.home()/rel).is_file(), 'local asset ' + rel)
    if shutil.which('systemctl'):
        for filename, flags in [('system-services.txt', []), ('user-services.txt', ['--user'])]:
            missing = [u for u in lines(ROOT/'bootstrap'/filename) if run('systemctl', *flags, 'is-enabled', u).returncode]
            check(not missing, filename + (': not enabled ' + ', '.join(missing) if missing else ' enabled'))
    dirty = run('git', '-C', str(ROOT), 'status', '--porcelain').stdout
    check(not dirty, 'checkout clean: remote installs cannot include uncommitted/untracked work')
    print('Private app backups, authentication, hardware, and graphical smoke tests remain manual: dotfiles.md')
    return bool(problems)


if __name__ == '__main__':
    sys.exit(main())
