import pathlib, unittest
from unittest.mock import patch
from PIL import Image
import attention as a

class AttentionTests(unittest.TestCase):
    def test_windowed_pause_menu_is_recognized_before_input(self):
        im=Image.new('L',(720,480))
        fixture=pathlib.Path(__file__).parent/'testdata/expedition33-windowed-menu.png'
        im.paste(Image.open(fixture),(0,0))
        profile={'mode':'auto-expedition33','modes':{'gameplay':{'enabled':True,'key':'Escape','detector':'expedition33-menu'},'cutscene':{'enabled':True,'key':'f','detector':'expedition33-pause'}}}
        with patch.object(a,'screen',return_value=im),patch.object(a,'run') as run,patch.object(a,'dispatch') as dispatch:
            ok,detail=a.pause_game(profile,{})
            self.assertTrue(ok);self.assertEqual(detail,'gameplay already paused')
            run.assert_not_called();dispatch.assert_not_called()

    def test_blank_screen_is_not_pause_menu(self):
        self.assertLess(a.menu_score(Image.new('L',(720,480))),.60)

    def test_status_transitions(self):
        self.assertEqual(a.reason({'type':'active'}, {'type':'idle'}),'finished')
        self.assertIsNone(a.reason(None,{'type':'idle'}))
        self.assertIsNone(a.reason({'type':'idle'},{'type':'idle'}))
        waiting={'type':'active','activeFlags':['waitingOnApproval']}
        self.assertEqual(a.reason({'type':'active','activeFlags':[]},waiting),'approval requested')
        self.assertIsNone(a.reason(waiting,waiting))
        self.assertEqual(a.reason(None,{'type':'active','activeFlags':['waitingOnUserInput']}),'answer requested')

    def test_no_repeated_pause_for_duplicate_events(self):
        r=a.Router(); e={'source':'Claude','session':'test','event':'finished','name':'work'}
        moon={'class':'Moonlight','title':'host - Moonlight','address':'a'}
        c={'enabled':True,'active_game':'game','games':{'game':{}},'cooldown_seconds':15}
        c['games']['game']={'modes':{}}
        with patch.object(a,'config',return_value=c),patch.object(a,'hypr',return_value=moon),patch.object(a,'resolve_target',return_value={'address':'b'}),patch.object(a,'pause_game',return_value=(True,'paused')) as pause,patch.object(a,'focus') as focus,patch.object(a,'notify'):
            r.handle(e);r.handle(e)
            self.assertEqual(pause.call_count,1);self.assertEqual(focus.call_count,1)

    def test_unconfirmed_pause_never_switches(self):
        r=a.Router();e={'source':'Claude','session':'test','event':'finished'}
        moon={'class':'Moonlight','title':'host - Moonlight','address':'a'}
        with patch.object(a,'config',return_value={'enabled':True,'active_game':'game','games':{'game':{'modes':{}}}}),patch.object(a,'hypr',return_value=moon),patch.object(a,'resolve_target',return_value={'address':'b'}),patch.object(a,'pause_game',return_value=(False,'not confirmed')),patch.object(a,'focus') as focus,patch.object(a,'notify'):
            r.handle(e);focus.assert_not_called()

    def test_already_paused_does_not_send_key(self):
        profile={'mode':'cutscene','modes':{'cutscene':{'enabled':True,'key':'f','detector':'expedition33-pause'}}}
        with patch.object(a,'screen'),patch.object(a,'pause_score',return_value=.9),patch.object(a,'dispatch') as dispatch:
            self.assertTrue(a.pause_game(profile,{})[0]);dispatch.assert_not_called()

    def test_missing_profile_never_sends_input(self):
        r=a.Router();e={'source':'Claude','session':'test','event':'finished'}
        with patch.object(a,'config',return_value={'enabled':True}),patch.object(a,'hypr',return_value={'class':'Moonlight','title':'host - Moonlight'}),patch.object(a,'resolve_target',return_value={'address':'b'}),patch.object(a,'pause_game') as pause,patch.object(a,'notify'):
            r.handle(e);pause.assert_not_called()

    def test_disabled_does_nothing(self):
        with patch.object(a,'config',return_value={'enabled':False}),patch.object(a,'hypr') as hypr:
            a.Router().handle({});hypr.assert_not_called()

if __name__=='__main__':unittest.main()
