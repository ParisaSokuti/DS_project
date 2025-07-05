import pytest
import asyncio
import json
from types import SimpleNamespace

from backend.server import GameServer

class DummyWS:
    def __init__(self):
        self.sent = []
    async def send(self, msg):
        self.sent.append(msg)

class DummyNetwork:
    def __init__(self):
        self.connection_metadata = {}
        self.live_connections = {}
        self._ws = DummyWS()
    def register_connection(self, ws, player_id, room):
        self.live_connections[ws] = player_id
        self.connection_metadata[ws] = {'player_id': player_id, 'room_code': room}
    def get_live_connection(self, pid):
        return self._ws
    async def broadcast_to_room(self, room_code, message_type, data, redis_manager=None):
        # simulate JSON serialization check
        json.dumps(data)
    async def send_message(self, ws, message_type, data):
        await ws.send(f"MSG:{message_type}")
    async def notify_error(self, ws, msg):
        await ws.send(f"ERR:{msg}")

class DummyRedis:
    def get_room_players(self, room):
        return [{'player_id':'p1','username':'U1'}]
    def save_game_state(self, *args, **kwargs):
        pass

@pytest.mark.asyncio
async def test_handle_play_card_with_none_team_tricks():
    # Arrange
    gs = GameServer()
    gs.network_manager = DummyNetwork()
    gs.redis_manager = DummyRedis()
    room = "R1"
    # inject an active game with minimal attributes
    game = SimpleNamespace(
        players=['U1'],
        current_turn=0,
        hands={'U1':['A_hearts']},
        teams={'U1':0},
        hokm='hearts',
        to_redis_dict=lambda: {}
    )
    def fake_play_card(player, card, rm):
        return {
            'valid': True,
            'trick_complete': True,
            'hand_complete': True,
            'trick_winner': 'U1',
            'team_tricks': None,          # bad data
            'round_winner': 2,
            'round_scores': None,         # bad data
            'game_complete': False
        }
    game.play_card = fake_play_card
    gs.active_games[room] = game

    # Mock find_player_by_websocket to return valid player info
    def mock_find_player(websocket, room_code):
        return 'U1', 'p1'
    gs.find_player_by_websocket = mock_find_player

    # Create a dummy ws and register it
    ws = gs.network_manager._ws
    gs.network_manager.register_connection(ws, 'p1', room)

    msg = {'type':'play_card','room_code':room,'player_id':'p1','card':'A_hearts'}

    # Act / Assert: should not raise, and broadcasts should work despite bad data
    try:
        await gs.handle_play_card(ws, msg)
        print("✅ handle_play_card completed without raising an exception")
    except Exception as e:
        pytest.fail(f"handle_play_card raised an exception: {e}")
    
    # The key test is that no exception was raised - the connection stays open
