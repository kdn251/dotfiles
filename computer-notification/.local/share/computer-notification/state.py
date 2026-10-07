"""Pure, testable completion deduplication. No persisted/replayed backlog."""
from pathlib import PurePosixPath


def completion_label(agent):
    project = PurePosixPath(agent.get('cwd') or '').name or 'Pi'
    project = ''.join(c for c in project if c.isprintable()) or 'Pi'
    if len(project) > 32:
        project = project[:31] + '…'
    if agent.get('tab_id'):
        location = 'tab ' + agent['tab_id']
    else:
        location = 'pane ' + agent['pane_id']
    return f'{project} · {location}'


def detail_text(labels, total):
    recent = labels[-2:]
    extra = max(0, total - len(recent))
    return '\n'.join(recent + ([f'+{extra} other completions'] if extra else []))


class Completions:
    def __init__(self):
        self.previous = {}

    def update(self, agents, baseline=False):
        current = {}
        ready = []
        for agent in agents:
            key = (agent['pane_id'], agent.get('terminal_id'),
                   agent.get('agent_session', {}).get('value'))
            seq = agent.get('completion_seq') or 0
            current[key] = seq
            old = self.previous.get(key)
            if (not baseline and old is not None and seq > old
                    and agent.get('agent_status') in ('idle', 'done')):
                ready.append(agent)
        self.previous = current
        return ready
