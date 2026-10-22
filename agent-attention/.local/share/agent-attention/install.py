#!/usr/bin/env python3
"""Restore the attention service without overwriting unrelated Claude settings."""
import argparse, datetime, json, os, pathlib, shutil, subprocess

def install(home, start):
    package = pathlib.Path(__file__).resolve().parents[3]
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = home / '.local/state/agent-attention/backups' / stamp
    def preserve(path):
        dst = backup / path.relative_to(home)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
    files = [p for root in (package/'.local', package/'.config') for p in root.rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    for src in files:
        rel = src.relative_to(package); dst = home / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() and dst.resolve() == src: continue
        if dst.exists():
            # Preserve machine-specific game profiles on repeat installations.
            if str(rel) == '.config/agent-attention/config.json' and dst.read_bytes() != src.read_bytes():
                print('Keeping existing game profiles:', dst); continue
            if dst.is_dir(): raise RuntimeError(f'Expected a file: {dst}')
            preserve(dst)
        if dst.exists() or dst.is_symlink(): dst.unlink()
        dst.symlink_to(src)
    settings = home / '.claude/settings.json'
    settings.parent.mkdir(parents=True, exist_ok=True)
    original = settings.read_text() if settings.exists() else None
    data = json.loads(original) if original else {}
    hooks = data.setdefault('hooks', {})
    command = '"$HOME/.local/bin/agent-attention" claude-hook'
    for event, matcher in [('Stop',None),('PermissionRequest',None),
                           ('Notification','permission_prompt|idle_prompt|elicitation_dialog'),
                           ('PreToolUse','AskUserQuestion'),('Elicitation',None)]:
        remaining = []
        for group in hooks.get(event, []):
            group = dict(group)
            group['hooks'] = [h for h in group.get('hooks', []) if 'agent-attention' not in h.get('command','')]
            if group['hooks']: remaining.append(group)
        entry = {'hooks':[{'type':'command','command':command,'timeout':5}]}
        if matcher: entry['matcher'] = matcher
        hooks[event] = remaining + [entry]
    updated = json.dumps(data, indent=2)+'\n'
    if updated != original:
        if original is not None: preserve(settings)
        temporary = settings.with_name('settings.agent-attention.tmp')
        temporary.write_text(updated); temporary.chmod(0o600); temporary.replace(settings)
    if start:
        subprocess.run(['systemctl','--user','daemon-reload'],check=True)
        subprocess.run(['systemctl','--user','enable','--now','agent-attention.service'],check=True)
        subprocess.run(['systemctl','--user','restart','agent-attention.service'],check=True)
    print('Installed Agent Attention. Game profiles:', home/'.config/agent-attention/config.json')
    print('Recheck pause detection on a new monitor/game layout before relying on automatic switching.')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=pathlib.Path,default=pathlib.Path.home())
    parser.add_argument('--no-start',action='store_true',help='Link/configure files without starting user services')
    args=parser.parse_args()
    if args.home.resolve()!=pathlib.Path.home().resolve() and not args.no_start:
        parser.error('--home with a different home requires --no-start')
    install(args.home.resolve(),not args.no_start)
