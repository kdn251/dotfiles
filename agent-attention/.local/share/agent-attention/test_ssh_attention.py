import json,pathlib,tempfile,unittest
from unittest.mock import patch
from ssh_remote import build_event
from ssh_attention import address,command
from install_ssh_remote import install

class SSHAttentionTests(unittest.TestCase):
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
