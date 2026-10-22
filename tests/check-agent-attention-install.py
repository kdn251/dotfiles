#!/usr/bin/env python3
"""Check fresh/repeated restores and preservation of existing user preferences."""
import json, pathlib, subprocess, sys, tempfile
repo=pathlib.Path(__file__).resolve().parents[1]
installer=repo/'agent-attention/.local/share/agent-attention/install.py'
with tempfile.TemporaryDirectory(prefix='agent-attention-install-') as tmp:
    home=pathlib.Path(tmp);settings=home/'.claude/settings.json'
    settings.parent.mkdir();settings.write_text(json.dumps({'theme':'dark','hooks':{'Stop':[{'hooks':[{'type':'command','command':'echo existing'}]}]}}))
    def install():subprocess.run([sys.executable,str(installer),'--home',str(home),'--no-start'],check=True,stdout=subprocess.DEVNULL)
    install();first=settings.read_text();install();assert settings.read_text()==first,'Installer must be idempotent'
    data=json.loads(first);assert data['theme']=='dark'
    handlers=[h for g in data['hooks']['Stop'] for h in g['hooks']]
    assert any(h['command']=='echo existing' for h in handlers)
    assert sum('agent-attention' in h['command'] for h in handlers)==1
    assert (home/'.local/bin/agent-attention').is_symlink()
    service=(home/'.config/systemd/user/agent-attention.service').read_text()
    assert '%h/.local/bin/agent-attention' in service and '/home/knaught' not in service
    assert '$HOME' in handlers[-1]['command']
    profile=home/'.config/agent-attention/config.json'
    profile.unlink();profile.write_text('{"enabled": false, "custom": true}\n')
    install();assert json.loads(profile.read_text())=={'enabled':False,'custom':True}
    assert not profile.is_symlink(),'Custom profiles must not be replaced'
    assert list((home/'.local/state/agent-attention/backups').rglob('settings.json'))
print('PASS: fresh restore, repeat restore, portable paths, hook merge, backups, custom-profile preservation')
