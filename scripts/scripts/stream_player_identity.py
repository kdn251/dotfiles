"""Dynamic identity for a reusable live-stream MPV window."""
from media_chat_fullscreen import ipc, socket_for

def identity(player):
    try:
        endpoint = socket_for(player)
        if not endpoint:
            return None
        state = {'socket': endpoint, 'player': player}
        service = ipc(state, 'get_property', 'user-data/stream-service')
        name = ipc(state, 'get_property', 'user-data/stream-name')
        return (service, name) if service in ('Twitch', 'YouTube', 'Kick', 'Rumble') else None
    except (OSError, ValueError):
        return None


def expanded_chat_target(player):
    """Chat identity is separate from the native decoder's stream identity."""
    try:
        endpoint=socket_for(player)
        if not endpoint:return None
        state={'socket':endpoint,'player':player}
        target=ipc(state,'get_property','user-data/stream-multiview-chat')
        return target if isinstance(target,dict) and target.get('service') in ('Twitch','YouTube','Kick','Rumble') and target.get('name') else None
    except (OSError,ValueError):return None


def chat_identity(player):
    target=expanded_chat_target(player)
    return (target['service'],target['name']) if target else identity(player)
