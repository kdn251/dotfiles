import unittest
from herdr_attention import Tracker,ssh_command
from herdr_remote import matches

def agent(state='idle',seq=1,session='s1',terminal='t1'):
    return dict(agent='claude',pane_id='w1:p1',terminal_id=terminal,agent_session={'value':session},agent_status=state,completion_seq=seq)

class HerdrAttentionTests(unittest.TestCase):
    def test_no_startup_backlog(self):
        t=Tracker();self.assertEqual(t.update([agent(seq=30)]),[]);self.assertEqual(t.update([agent(seq=30)]),[])
    def test_completion_settles_and_deduplicates(self):
        t=Tracker();t.update([agent('working',2)])
        self.assertEqual(t.update([agent('done',3)]),[])
        self.assertEqual(t.update([agent('idle',3)])[0][1],'finished')
        self.assertEqual(t.update([agent('idle',3)]),[])
    def test_transient_ready_does_not_interrupt(self):
        t=Tracker();t.update([agent('working',2)]);t.update([agent('idle',3)])
        self.assertEqual(t.update([agent('working',4)]),[])
    def test_blocked_settles(self):
        t=Tracker();t.update([agent('working',2)]);self.assertEqual(t.update([agent('blocked',3)]),[])
        self.assertEqual(t.update([agent('blocked',3)])[0][1],'approval or answer requested')
        self.assertEqual(t.update([agent('blocked',3)]),[])
    def test_new_session_never_replays_old_completion(self):
        t=Tracker();t.update([agent('working',2)]);self.assertEqual(t.update([agent('idle',9,session='s2')]),[])
        self.assertEqual(t.update([agent('idle',9,session='s2')]),[])
    def test_focus_checks_session_and_terminal(self):
        expected={'pane':'w1:p1','terminal':'t1','session':'s1'}
        self.assertTrue(matches(agent(),expected));self.assertFalse(matches(agent(session='new'),expected));self.assertFalse(matches(agent(terminal='new'),expected))
    def test_ssh_does_not_forward_ports_or_interpolate_host(self):
        command=ssh_command({'host':'boole'},'watch')
        self.assertIn('ClearAllForwardings=yes',command);self.assertIn('BatchMode=yes',command)
        with self.assertRaises(ValueError):ssh_command({'host':'-oProxyCommand=bad'},'watch')

if __name__=='__main__':unittest.main()
