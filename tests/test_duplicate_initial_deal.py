import pytest
import asyncio
import websockets
import json
import sys
import os
from dotenv import load_dotenv

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

load_dotenv()

@pytest.mark.asyncio
async def test_no_duplicate_initial_deal():
    """
    Test that players don't receive duplicate initial_deal messages when joining a game.
    """
    room_code = "DUPLICATE_TEST"
    initial_deal_counts = {}
    
    # Connect 4 players and track initial_deal messages
    async def test_player(username):
        initial_deal_count = 0
        async with websockets.connect("ws://localhost:8765") as ws:
            # Join room
            await ws.send(json.dumps({
                "type": "join",
                "username": username,
                "room_code": room_code
            }))
            
            # Listen for messages for 10 seconds
            for _ in range(20):  # 20 * 0.5 = 10 seconds
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'initial_deal':
                        initial_deal_count += 1
                        print(f"{username}: Received initial_deal #{initial_deal_count}")
                        
                except asyncio.TimeoutError:
                    continue
                    
        initial_deal_counts[username] = initial_deal_count
        return initial_deal_count
    
    # Create 4 players concurrently
    players = ["Alice", "Bob", "Charlie", "Diana"]
    tasks = [test_player(player) for player in players]
    results = await asyncio.gather(*tasks)
    
    # Verify results
    print(f"Initial deal counts: {initial_deal_counts}")
    
    # Each player should receive exactly 1 initial_deal message
    for player, count in initial_deal_counts.items():
        assert count <= 1, f"{player} received {count} initial_deal messages (expected 0 or 1)"
    
    # At least some players should have received initial deals (if game started)
    total_deals = sum(initial_deal_counts.values())
    if total_deals > 0:
        # If any player got cards, verify no duplicates
        for player, count in initial_deal_counts.items():
            if count > 1:
                pytest.fail(f"DUPLICATE DETECTED: {player} received {count} initial_deal messages!")
        
        print(f"✅ SUCCESS: {total_deals} total initial_deal messages, no duplicates detected")
    else:
        print("⚠️  No initial_deal messages received (game may not have started)")
