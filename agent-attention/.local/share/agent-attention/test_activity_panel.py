import unittest
from unittest.mock import patch
import activity_panel as p

class NavigationTests(unittest.TestCase):
    def test_background_has_no_focus_target(self):
        with patch.object(p.attention,'resolve_target') as resolve:
            self.assertIsNone(p.target_for({'background':True},[]));resolve.assert_not_called()

    def test_recycled_process_cannot_receive_focus(self):
        row={'agent':'Claude','host':'local','process':{'pid':123,'start':'old'}}
        with patch.object(p,'process_identity',return_value=(1,'new')),patch.object(p.attention,'process_target') as target:
            self.assertIsNone(p.target_for(row,[]));target.assert_not_called()

    def test_closed_session_rejected_before_focus(self):
        with patch.object(p,'snapshot',return_value={'agents':[]}),patch.object(p.attention,'focus') as focus:
            with self.assertRaises(RuntimeError):p.focus_row('boole','Codex','closed')
            focus.assert_not_called()

    def test_ssh_route_uses_selected_connection(self):
        connection=['100.1.1.1','123','100.2.2.2','22']
        row={'agent':'Codex','host':'boole','process':{'connection':connection}}
        with patch.object(p.attention,'resolve_target',return_value={'address':'exact'}) as resolve:
            self.assertEqual(p.target_for(row,[]),{'address':'exact'})
            self.assertEqual(resolve.call_args.args[0],{'ssh_route':{'host':'boole','connection':connection}})

if __name__=='__main__':unittest.main()
