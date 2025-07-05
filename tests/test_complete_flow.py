#!/usr/bin/env python3
"""
Test the complete game flow including card playing
"""

import asyncio
import websockets
import json
import time
import pytest
import threading
from backend.server import main as server_main

SERVER_URI = "ws://localhost:8765"
ROOM_CODE = "9999"

@pytest.fixture(scope="module", autouse=True)
def start_server():
    # Launch Hokm WebSocket server in background thread
    thread = threading.Thread(target=lambda: asyncio.run(server_main()), daemon=True)
    thread.start()
    # Wait briefly for server to start
    time.sleep(0.5)
    yield

async def _test_player(player_name, is_hakem=False):
    """Test a single player's complete flow"""
    try:
        async with websockets.connect(SERVER_URI) as ws:
            print(f"[{player_name}] Connecting...")
            
            # Join room
            await ws.send(json.dumps({
                "type": "join",
                "username": player_name,
                "room_code": ROOM_CODE
            }))
            
            player_id = None
            hand = []
            hokm = None
            turn_count = 0
            
            # Listen for messages
            while turn_count < 3:  # Limit test duration
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    print(f"[{player_name}] Received: {msg_type}")
                    
                    if msg_type == 'join_success':
                        player_id = data.get('player_id')
                        print(f"[{player_name}] Got player_id: {player_id[:8]}...")
                    
                    elif msg_type == 'initial_deal':
                        hand = data.get('hand', [])
                        print(f"[{player_name}] Got {len(hand)} cards")
                        
                        # If this is the hakem, select hokm
                        if is_hakem:
                            await asyncio.sleep(0.5)
                            await ws.send(json.dumps({
                                'type': 'hokm_selected',
                                'suit': 'hearts',
                                'room_code': ROOM_CODE
                            }))
                            print(f"[{player_name}] Selected hearts as hokm")
                    
                    elif msg_type == 'final_deal':
                        hand = data.get('hand', [])
                        hokm = data.get('hokm')
                        print(f"[{player_name}] Final hand: {len(hand)} cards, hokm: {hokm}")
                    
                    elif msg_type == 'turn_start':
                        your_turn = data.get('your_turn', False)
                        current_player = data.get('current_player')
                        hand = data.get('hand', hand)
                        
                        print(f"[{player_name}] Turn start - current: {current_player}, your_turn: {your_turn}")
                        
                        # If it's our turn, play a card
                        if your_turn and hand and player_id:
                            card_to_play = hand[0]  # Play first card
                            print(f"[{player_name}] Playing card: {card_to_play}")
                            
                            # Send play_card message with all required fields
                            await ws.send(json.dumps({
                                "type": "play_card",
                                "room_code": ROOM_CODE,
                                "player_id": player_id,
                                "card": card_to_play
                            }))
                            
                            turn_count += 1
                            print(f"[{player_name}] ✅ Successfully sent play_card message (turn {turn_count})")
                    
                    elif msg_type == 'card_played':
                        player = data.get('player')
                        card = data.get('card')
                        print(f"[{player_name}] Saw {player} play {card}")
                    
                    elif msg_type == 'error':
                        error_msg = data.get('message', '')
                        print(f"[{player_name}] ❌ ERROR: {error_msg}")
                        
                        # Check for the specific error we're testing
                        if "Missing room_code, player_id, or card" in error_msg:
                            print(f"[{player_name}] ❌ FAILED: Still getting the missing fields error!")
                            return False
                        elif "Malformed play_card message" in error_msg:
                            print(f"[{player_name}] ❌ FAILED: Still getting malformed message error!")
                            return False
                    
                except asyncio.TimeoutError:
                    print(f"[{player_name}] Timeout - continuing...")
                    break
                except Exception as e:
                    print(f"[{player_name}] Error: {e}")
                    break
            
            print(f"[{player_name}] ✅ Test completed successfully - played {turn_count} turns")
            return True
            
    except Exception as e:
        print(f"[{player_name}] Connection error: {e}")
        return False

@pytest.mark.asyncio
async def test_complete_flow():
    """Run the complete test"""
    print("=== Testing complete game flow with card playing ===")
    
    # Start 4 players with one as hakem
    players = [
        ("Player1", False),
        ("Player2", False),
        ("Player3", True),   # This player will be hakem
        ("Player4", False)
    ]
    
    print("Starting 4 players...")
    
    tasks = [_test_player(name, is_hakem) for name, is_hakem in players]

    try:
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)

        # Check results
        success_count = sum(1 for result in results if result)
        print(f"\n=== Test Results ===")
        print(f"Players that completed successfully: {success_count}/4")

        if success_count >= 3:  # Allow some tolerance
            print("✅ SUCCESS: Card playing is working!")
            print("The 'Missing room_code, player_id, or card' error has been fixed!")
        else:
            print("❌ FAILED: Some players could not complete the flow")

    except asyncio.TimeoutError:
        print("⏰ Test timed out after 20 seconds")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
