import json
from pathlib import Path
import unittest
from state import Completions, NeedsAttention, completion_label, detail_text, popup_title


def agent(seq=10, status='idle', pane='w1:p1', terminal='t1', session='s1'):
    return dict(pane_id=pane, terminal_id=terminal, completion_seq=seq,
                agent_status=status, agent_session={'value': session})


class AttentionTests(unittest.TestCase):
    def test_blocked_once(self):
        detector = NeedsAttention()
        self.assertEqual(detector.update([agent(status='working')], baseline=True), [])
        self.assertEqual(len(detector.update([agent(status='blocked')])), 1)
        self.assertEqual(detector.update([agent(status='blocked')]), [])
        self.assertEqual(detector.update([agent(status='working')]), [])
        self.assertEqual(len(detector.update([agent(status='blocked')])), 1)

    def test_no_startup_or_reconnect_replay(self):
        detector = NeedsAttention()
        self.assertEqual(detector.update([agent(status='blocked')]), [])
        detector.update([agent(status='working')])
        self.assertEqual(detector.update([agent(status='blocked')], baseline=True), [])
        self.assertEqual(detector.update([agent(status='blocked')]), [])

    def test_replaced_session_not_attention(self):
        detector = NeedsAttention()
        detector.update([agent(status='working')], baseline=True)
        self.assertEqual(detector.update([agent(status='blocked', session='new')]), [])

    def test_completion_and_attention_are_distinct(self):
        completion, attention = Completions(), NeedsAttention()
        for detector in (completion, attention):
            detector.update([agent(status='working')], baseline=True)
        self.assertEqual(completion.update([agent(None, 'blocked')]), [])
        self.assertEqual(len(attention.update([agent(None, 'blocked')])), 1)
        self.assertEqual(len(completion.update([agent(12, 'idle')])), 1)
        self.assertEqual(attention.update([agent(12, 'idle')]), [])

    def test_titles(self):
        self.assertEqual(popup_title(1, 0), 'Clanker is ready')
        self.assertEqual(popup_title(1, 1), 'Clanker needs attention')
        self.assertEqual(popup_title(2, 2), '2 Clankers need attention')
        self.assertEqual(popup_title(2, 1), '2 Clanker updates')


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.detector = Completions()
        self.assertEqual(self.detector.update([agent()], baseline=True), [])

    def test_initial_idle_not_completion(self):
        self.assertEqual(self.detector.update([agent()]), [])

    def test_complete_once(self):
        self.assertEqual(len(self.detector.update([agent(11)])), 1)
        self.assertEqual(self.detector.update([agent(11)]), [])

    def test_tool_round_not_completion(self):
        self.assertEqual(self.detector.update([agent(10, 'working')]), [])
        self.assertEqual(self.detector.update([agent(10, 'working')]), [])
        self.assertEqual(len(self.detector.update([agent(11)])), 1)

    def test_working_clears_optional_completion_seq(self):
        self.assertEqual(self.detector.update([agent(None, 'working')]), [])
        self.assertEqual(len(self.detector.update([agent(12)])), 1)
        self.assertEqual(self.detector.update([agent(12)]), [])

    def test_missing_completion_seq(self):
        working = agent(status='working')
        del working['completion_seq']
        self.assertEqual(self.detector.update([working]), [])
        self.assertEqual(len(self.detector.update([agent(12)])), 1)

    def test_blocked_not_completion(self):
        self.assertEqual(self.detector.update([agent(11, 'blocked')]), [])

    def test_reconnect_does_not_replay(self):
        self.assertEqual(self.detector.update([agent(50)], baseline=True), [])
        self.assertEqual(self.detector.update([agent(50)]), [])
        self.assertEqual(len(self.detector.update([agent(51)])), 1)

    def test_replacement_does_not_replay(self):
        self.assertEqual(self.detector.update([agent(20, terminal='t2')]), [])
        self.assertEqual(self.detector.update([agent(30, terminal='t2', session='s2')]), [])

    def test_closed_pane_dropped(self):
        self.detector.update([])
        self.assertEqual(self.detector.update([agent(20)]), [])

    def test_new_agent_baselined(self):
        self.assertEqual(self.detector.update([agent(), agent(20, pane='w1:p2')]), [])
        self.assertEqual(len(self.detector.update([agent(11), agent(21, pane='w1:p2')])), 2)

    def test_new_working_baseline_can_complete(self):
        self.detector.update([agent(10, 'working')], baseline=True)
        self.assertEqual(len(self.detector.update([agent(11)])), 1)

    def test_project_and_tab_label(self):
        self.assertEqual(completion_label(dict(cwd='/home/me/projects/ferryman',
                                              tab_id='w9:t7', tab_label='2', pane_id='w9:p8')),
                         'ferryman · tab 2')

    def test_label_fallback_and_plain_text(self):
        self.assertEqual(completion_label(dict(pane_id='w1:p2', tab_id='w1:t1')), 'Pi')
        self.assertEqual(completion_label(dict(cwd='/tmp/<hello>\n', pane_id='p')),
                         '<hello>')

    def test_named_tab_not_internal_id(self):
        label = completion_label(dict(cwd='/work/ferryman', tab_id='w9:tA',
                                      tab_label='Frontend', pane_id='w9:pB'))
        self.assertEqual(label, 'ferryman · tab Frontend')
        self.assertNotIn('w9:', label)

    def test_multiple_completion_details(self):
        self.assertEqual(detail_text(['a', 'b', 'c'], 4), 'b\nc\n+2 other updates')
        self.assertEqual(detail_text(['a'], 1), 'a')

    def test_frames(self):
        frames = json.loads((Path(__file__).parent / 'frames.json').read_text())['frames']
        self.assertEqual({f['phase'] for f in frames}, {'travel', 'insert', 'read', 'happy'})
        self.assertEqual(frames[-1]['phase'], 'happy')
        for frame in frames:
            self.assertEqual(len(frame['pixels']), 26)
            self.assertTrue(all(len(row) == 38 for row in frame['pixels']))


if __name__ == '__main__':
    unittest.main()
