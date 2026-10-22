import json,pathlib,tempfile,unittest
from activity import summarize
from activity_probe import Probe,claude_state,install_hooks

class ActivityTests(unittest.TestCase):
    def test_aggregate_hosts_waiting_and_stale_monitors(self):
        sources={'local':{'host':'local','updated':100,'items':[{'id':'a','agent':'Codex','state':'working'}]},
                 'ssh:boole':{'host':'boole','updated':100,'items':[{'id':'b','agent':'Claude','state':'attention'}]}}
        result=summarize(sources,101)
        self.assertEqual((result['state'],result['working'],result['waiting']),('working',1,1))
        sources['local']['items']=[]
        self.assertEqual(summarize(sources,101)['state'],'attention')
        self.assertEqual(summarize(sources,110)['state'],'unknown')
        sources['ssh:boole']['items']=[]
        self.assertEqual(summarize(sources,101)['state'],'idle')

    def test_api_precedence_and_no_duplicate_agents(self):
        a={'id':'same','agent':'Codex','state':'working','activity':90}
        sources={'local-probe':{'host':'local','updated':100,'items':[a]},
                 'local-codex':{'host':'local','updated':100,'items':[{**a,'state':'attention','activity':None}]}}
        for order in (sources,dict(reversed(list(sources.items())))):
            result=summarize(order,101)
            self.assertEqual(result['working'],0);self.assertEqual(result['waiting'],1)
            self.assertEqual(result['agents'][0]['activity'],90)

    def test_incremental_rollout_tracks_turns_and_partial_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'rollout.jsonl';probe=Probe()
            def append(kind,payload):
                with path.open('a') as f:f.write(json.dumps({'type':kind,'payload':payload,'timestamp':'2026-10-22T12:00:00Z'})+'\n')
            append('session_meta',{'id':'a','source':'cli'})
            append('event_msg',{'type':'task_started'})
            self.assertEqual(probe.rollout(path)['state'],'working')
            append('response_item',{'phase':'commentary','content':['not exported']})
            self.assertNotIn('not exported',json.dumps(probe.rollout(path)))
            with path.open('a') as f:f.write('{"type":"event_msg","payload":{"type":"task_complete"}}')
            self.assertEqual(probe.rollout(path)['state'],'working')
            with path.open('a') as f:f.write('\n')
            self.assertEqual(probe.rollout(path)['state'],'idle')
            append('event_msg',{'type':'task_started'})
            self.assertEqual(probe.rollout(path)['state'],'working')

    def test_internal_threads_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'rollout.jsonl'
            path.write_text(json.dumps({'type':'session_meta','payload':{'id':'a','source':{'subagent':'x'}}})+'\n')
            self.assertIsNone(Probe().rollout(path))

    def test_claude_lifecycle_and_hook_merge(self):
        self.assertEqual(claude_state({'hook_event_name':'UserPromptSubmit'}),'working')
        self.assertEqual(claude_state({'hook_event_name':'PermissionRequest'}),'attention')
        self.assertEqual(claude_state({'hook_event_name':'PostToolUse'}),'working')
        self.assertEqual(claude_state({'hook_event_name':'Stop'}),'idle')
        self.assertIsNone(claude_state({'hook_event_name':'Notification','notification_type':'idle_prompt'}))
        data={'hooks':{'Stop':[{'hooks':[{'command':'keep-me'}]}]}}
        install_hooks(data,'python3 activity_probe.py claude-hook');before=json.dumps(data)
        install_hooks(data,'python3 activity_probe.py claude-hook')
        self.assertEqual(before,json.dumps(data));self.assertIn('keep-me',before)

if __name__=='__main__':unittest.main()
