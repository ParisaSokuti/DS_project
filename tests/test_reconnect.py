import pytest
import asyncio
import websockets
import json
from dotenv import load_dotenv

load_dotenv()

@pytest.mark.asyncio
async def test_player_reconnection():
    """
    Test that a player can disconnect and reconnect, and receives their hand and game state.
    """
    room_code = "RECONNECT_TEST"
    player_id = None
    # Connect first player and join
    async with websockets.connect("ws://localhost:8765") as ws1:
        await ws1.send(json.dumps({
            "type": "join",
            "username": "Player1",
            "room_code": room_code
        }))
        response = await ws1.recv()
        resp_data = json.loads(response)
        assert resp_data["type"] == "join_success"
        player_id = resp_data["player_id"]

    # Simulate disconnect (context manager exits)
    await asyncio.sleep(0.5)

    # Reconnect with same player ID
    async with websockets.connect("ws://localhost:8765") as ws2:
        await ws2.send(json.dumps({
            "type": "reconnect",
            "player_id": player_id,
            "room_code": room_code
        }))
        # Should receive reconnect_success with hand and state
        state = await ws2.recv()
        state_data = json.loads(state)
        assert state_data["type"] == "reconnect_success"
        # Accept either top-level 'hand' or 'game_state' dict with 'hand'
        hand = state_data.get("hand")
        if hand is None and "game_state" in state_data:
            hand = state_data["game_state"].get("hand")
        assert hand is not None
        assert isinstance(hand, list)
        # Accept phase at top-level or in game_state
        phase = state_data.get("phase")
        if phase is None and "game_state" in state_data:
            phase = state_data["game_state"].get("phase")
        assert phase is not None
