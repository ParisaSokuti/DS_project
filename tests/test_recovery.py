import pytest
import asyncio
import websockets
import json
from dotenv import load_dotenv

load_dotenv()

@pytest.mark.asyncio
async def test_server_restart_recovery():
    """
    Test that after a server restart, the game state is recovered from Redis and players can reconnect and resume.
    """
    room_code = "RECOVERY_TEST"
    player_id = None
    # 1. Create game and join as one player
    async with websockets.connect("ws://localhost:8765") as ws:
        await ws.send(json.dumps({"type": "join", "room_code": room_code}))
        response = await ws.recv()
        resp_data = json.loads(response)
        assert resp_data["type"] == "join_success"
        player_id = resp_data["player_id"]
        # ...simulate more game actions if needed...

    # 2. Simulate server restart (manual step required)
    print("[MANUAL STEP] Please restart the server now to test recovery.")
    await asyncio.sleep(10)  # Give time for manual restart

    # 3. Reconnect and verify state
    async with websockets.connect("ws://localhost:8765") as ws:
        await ws.send(json.dumps({"type": "reconnect", "player_id": player_id, "room_code": room_code}))
        state = await ws.recv()
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
