"""Install the stdlib-only sender on the SSH host; preserve unrelated agent settings."""
import argparse,datetime,json,pathlib,re,shutil,sys,tomllib

def install(home,codex_full_access=False):
    home=pathlib.Path(home);root=home/'.local/share/agent-attention-ssh';root.mkdir(parents=True,exist_ok=True)
    source=pathlib.Path(__file__).resolve().with_name('ssh_remote.py');destination=root/'ssh_remote.py'
    if source!=destination:shutil.copy2(source,destination)
    backup=home/'.local/state/agent-attention-ssh/backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    def write(path,text):
        old=path.read_text() if path.exists() else None
        if old==text:return
        if old is not None:
            saved=backup/path.relative_to(home);saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,saved)
        path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.attention-tmp');tmp.write_text(text);tmp.chmod(0o600);tmp.replace(path)
    # Codex's documented notify callback works on the older CLI without enabling hooks.
    codex=home/'.codex/config.toml';original=codex.read_text() if codex.exists() else '';data=tomllib.loads(original)
    expected=['python3',str(destination),'codex-notify'];existing=data.get('notify')
    if existing is not None and existing!=expected:raise RuntimeError('Existing Codex notify command must be explicitly composed before installation')
    updated=original
    if existing is None:updated='notify = '+json.dumps(expected)+'\n'+updated
    if codex_full_access:
        # Explicit restore option for Kevin's chosen boole defaults.
        if isinstance(data.get('approval_policy'),dict):raise RuntimeError('Merge granular approval policy explicitly before enabling full access')
        for key,value in [('approval_policy','never'),('sandbox_mode','danger-full-access')]:
            if key in data:
                updated,count=re.subn(r'^'+key+r'\s*=.*$',key+' = '+json.dumps(value),updated,count=1,flags=re.M)
                if not count:raise RuntimeError('Cannot safely update '+key)
            else:updated=key+' = '+json.dumps(value)+'\n'+updated
    tomllib.loads(updated)
    write(codex,updated)
    claude=home/'.claude/settings.json';data=json.loads(claude.read_text()) if claude.exists() else {};hooks=data.setdefault('hooks',{})
    command='python3 "$HOME/.local/share/agent-attention-ssh/ssh_remote.py" claude-hook'
    for event,matcher in [('Stop',None),('PermissionRequest',None),('Notification','permission_prompt|idle_prompt|elicitation_dialog'),('PreToolUse','AskUserQuestion'),('Elicitation',None)]:
        groups=[]
        for old in hooks.get(event,[]):
            group=dict(old);group['hooks']=[h for h in group.get('hooks',[]) if 'agent-attention-ssh/ssh_remote.py' not in h.get('command','')]
            if group['hooks']:groups.append(group)
        entry={'hooks':[{'type':'command','command':command,'timeout':5}]}
        if matcher:entry['matcher']=matcher
        hooks[event]=groups+[entry]
    write(claude,json.dumps(data,indent=2)+'\n')
    # A shared Codex daemon retains the SSH environment of its first launcher.
    # Keep standalone interactive sessions attached to their own SSH connection.
    write(root/'codex-ssh.bash', '''# Managed by agent-attention-ssh/install_ssh_remote.py.
if [[ -n ${SSH_TTY-} && -z ${HERDR_ENV-}${HERDR_PANE_ID-}${TMUX-}${STY-} ]]; then
    if [[ $(command codex --help 2>/dev/null) == *"--no-daemon"* ]]; then
        alias codex='codex --no-daemon'
    fi
fi
''')
    bashrc=home/'.bashrc';original=bashrc.read_text() if bashrc.exists() else ''
    line='[[ -r "$HOME/.local/share/agent-attention-ssh/codex-ssh.bash" ]] && source "$HOME/.local/share/agent-attention-ssh/codex-ssh.bash"'
    if line not in original:write(bashrc,original.rstrip()+'\n\n# Keep standalone Codex attention events tied to this SSH terminal.\n'+line+'\n')
    print('Standalone SSH attention sender installed; start fresh Claude/Codex sessions to load callbacks.')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-full-access',action='store_true',help='Persist full filesystem/network access and no command approval prompts for Codex')
    args=parser.parse_args();install(pathlib.Path.home(),args.codex_full_access)
