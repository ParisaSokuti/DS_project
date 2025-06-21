import pytest
import asyncio
import websockets
import json
from dotenv import load_dotenv

load_dotenv()

@pytest.mark.asyncio
async def test_disconnect_during_hokm():
    """
    Test that if a player disconnects during hokm selection, the game is cancelled and all players are notified.
    """
    room_code = "EDGE_TEST"
    players = []
    # Start game with 3 players
    for i in range(3):
        ws = await websockets.connect("ws://localhost:8765")
        await ws.send(json.dumps({"type": "join", "room_code": room_code}))
        players.append(ws)
    # Simulate 4th player join and immediate disconnect during hokm selection
    async with websockets.connect("ws://localhost:8765") as ws:
        await ws.send(json.dumps({"type": "join", "room_code": room_code}))
        await ws.close()
    # All players should receive a game_cancelled or error message
    for p in players:
        # Skip initial join_success or other messages, wait for game_cancelled or error
        while True:
            response = await p.recv()
            resp_data = json.loads(response)
            msg_type = resp_data.get("type")
            if msg_type in ("game_cancelled", "error"):
                break
            # ignore other message types
        # Now assert cancellation notification received
        assert msg_type in ("game_cancelled", "error")
    # Cleanup: close all sockets
    for p in players:
        await p.close()
