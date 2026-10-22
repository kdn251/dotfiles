import json,os,pathlib,subprocess,tempfile,unittest
from unittest.mock import patch
from ssh_remote import build_event,codex_user_turn_complete
from ssh_attention import address,command
from install_ssh_remote import install

class SSHAttentionTests(unittest.TestCase):
    def test_full_access_restore_is_explicit_and_repeatable(self):
        import tomllib
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'.codex').mkdir()
            config=root/'.codex/config.toml'
            config.write_text('approval_policy = "on-request"\nsandbox_mode = "workspace-write"\nmodel = "existing"\n')
            install(root)
            self.assertEqual(tomllib.loads(config.read_text())['approval_policy'],'on-request')
            install(root,codex_full_access=True);before=config.read_text()
            data=tomllib.loads(before)
            self.assertEqual(data['approval_policy'],'never')
            self.assertEqual(data['sandbox_mode'],'danger-full-access')
            self.assertEqual(data['model'],'existing')
            install(root,codex_full_access=True)
            self.assertEqual(before,config.read_text())

    def test_codex_only_notifies_completed_user_turns(self):
        sid='01a1644b-3172-7c92-8c77-f251651f9c74'
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);sessions=root/'sessions';sessions.mkdir()
            payload={'thread-id':sid,'turn-id':'turn1'}
            self.assertFalse(codex_user_turn_complete(payload,root))
            file=sessions/('rollout-'+sid+'.jsonl')
            records=[{'type':'session_meta','payload':{'id':sid,'source':'cli','thread_source':'user'}},
                     {'type':'event_msg','payload':{'type':'task_started','turn_id':'turn1'}},
                     {'type':'response_item','payload':{'role':'assistant','phase':'commentary'}}]
            def save():file.write_text(''.join(json.dumps(r)+'\n' for r in records))
            save();self.assertFalse(codex_user_turn_complete(payload,root))
            records.append({'type':'event_msg','payload':{'type':'task_complete','turn_id':'turn1'}})
            save();self.assertTrue(codex_user_turn_complete(payload,root))
            self.assertFalse(codex_user_turn_complete({**payload,'turn-id':'other'},root))
            records[0]['payload']['source']={'subagent':{'parent_thread_id':'parent'}}
            save();self.assertFalse(codex_user_turn_complete(payload,root))
            records[0]['payload']['source']='cli'
            records.append({'type':'event_msg','payload':{'type':'task_started','turn_id':'turn2'}})
            save();self.assertFalse(codex_user_turn_complete(payload,root))

    def test_ssh_shell_default_and_excluded_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);install(root)
            bashrc=(root/'.bashrc').read_text();install(root)
            self.assertEqual(bashrc,(root/'.bashrc').read_text())
            binary=root/'bin';binary.mkdir();codex=binary/'codex'
            codex.write_text('#!/bin/sh\nprintf "%s\\n" --no-daemon\n');codex.chmod(0o700)
            env={k:v for k,v in os.environ.items() if k not in ('SSH_TTY','HERDR_ENV','HERDR_PANE_ID','TMUX','STY')}
            env.update(HOME=str(root),PATH=str(binary)+':/usr/bin',SSH_TTY='/dev/pts/1')
            def check(extra):
                return subprocess.run(['bash','--noprofile','--norc','-c','source "$HOME/.local/share/agent-attention-ssh/codex-ssh.bash"; alias codex'],env={**env,**extra},capture_output=True,text=True)
            self.assertIn('codex --no-daemon',check({}).stdout)
            for excluded in ({'SSH_TTY':''},{'HERDR_ENV':'1'},{'HERDR_PANE_ID':'p1'},{'TMUX':'session'},{'STY':'session'}):
                self.assertNotEqual(check(excluded).returncode,0)
            codex.write_text('#!/bin/sh\necho legacy-cli\n')
            self.assertNotEqual(check({}).returncode,0)

    def env(self):return {'SSH_CONNECTION':'100.1.1.1 12345 100.2.2.2 22','SSH_TTY':'/dev/pts/3'}
    def test_herdr_and_multiplexers_excluded(self):
        for key,value in [('HERDR_ENV','1'),('HERDR_PANE_ID','w1:p1'),('TMUX','x'),('STY','x')]:
            e=self.env();e[key]=value
            self.assertIsNone(build_event('Claude',{'hook_event_name':'Stop'},e))
    def test_claude_payload_does_not_copy_conversation(self):
        event=build_event('Claude',{'hook_event_name':'Stop','session_id':'s','cwd':'/private/project','last_assistant_message':'secret'},self.env())
        self.assertEqual(event['name'],'project');self.assertNotIn('secret',json.dumps(event));self.assertEqual(event['event'],'finished')
    def test_codex_supported_events(self):
        self.assertIsNone(build_event('Codex',{'type':'approval-requested'},self.env()))
        event=build_event('Codex',{'type':'agent-turn-complete','thread-id':'x','input-messages':['secret']},self.env())
        self.assertEqual(event['session'],'x');self.assertNotIn('secret',json.dumps(event))
    def test_direct_interactive_ssh_required(self):
        self.assertIsNone(build_event('Claude',{'hook_event_name':'Stop'},{}))
        e=self.env();del e['SSH_TTY'];self.assertIsNone(build_event('Claude',{'hook_event_name':'Stop'},e))
    def test_tcp_address_decode(self):
        self.assertEqual(address('0100007F:0016'),('127.0.0.1',22))
        self.assertEqual(address('00000000000000000000000001000000:0016'),('::1',22))
    def test_ssh_alias_validation(self):
        self.assertIn('ClearAllForwardings=yes',command('boole'))
        with self.assertRaises(ValueError):command('-oProxyCommand=bad')
    def test_remote_installer_preserves_preferences_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'.claude').mkdir();(root/'.codex').mkdir()
            settings=root/'.claude/settings.json';settings.write_text(json.dumps({'model':'existing','hooks':{'SessionStart':[{'hooks':[{'command':'keep-me'}]}]}}))
            config=root/'.codex/config.toml';config.write_text('model = "existing"\n')
            install(root);before=settings.read_text();codex_before=config.read_text();install(root)
            self.assertEqual(before,settings.read_text());self.assertEqual(codex_before,config.read_text())
            self.assertEqual(json.loads(before)['model'],'existing');self.assertIn('keep-me',before)
            self.assertIn('model = "existing"',codex_before)
    def test_existing_notify_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'.codex').mkdir();p=root/'.codex/config.toml';p.write_text('notify = ["existing"]\n')
            with self.assertRaises(RuntimeError):install(root)
            self.assertEqual(p.read_text(),'notify = ["existing"]\n')
if __name__=='__main__':unittest.main()
