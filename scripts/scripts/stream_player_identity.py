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
