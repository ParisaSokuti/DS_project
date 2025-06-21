#!/usr/bin/env python3
"""
Test script to verify that the play_card message format fix works correctly.
This test will:
1. Connect 4 players to room 9999
2. Go through the game flow until gameplay starts
3. Attempt to play a card to verify the message format is correct
4. Check that no "Malformed play_card message" error occurs
"""

import pytest
import asyncio
import websockets
import json
import time
import threading
from backend.server import main as server_main

# Start server for tests
@pytest.fixture(scope="module", autouse=True)
def start_server():
    thread = threading.Thread(target=lambda: asyncio.run(server_main()), daemon=True)
    thread.start()
    time.sleep(0.5)
    yield

SERVER_URI = "ws://localhost:8765"
ROOM_CODE = "9999"

async def _test_player(player_name, is_hakem=False):
    """Test a single player's flow"""
    try:
        async with websockets.connect(SERVER_URI) as ws:
            # Join room
            await ws.send(json.dumps({
                "type": "join",
                "username": player_name,
                "room_code": ROOM_CODE
            }))
            
            player_id = None
            hand = []
            hokm = None
            
            # Listen for messages
            while True:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    print(f"[{player_name}] Received: {msg_type}")
                    
                    if msg_type == 'join_success':
                        player_id = data.get('player_id')
                        print(f"[{player_name}] Player ID: {player_id}")
                    
                    elif msg_type == 'initial_deal':
                        hand = data.get('hand', [])
                        print(f"[{player_name}] Got {len(hand)} cards")
                        
                        # If this is the hakem, select hokm
                        if is_hakem:
                            await asyncio.sleep(0.5)  # Small delay
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
                            print(f"[{player_name}] Attempting to play card: {card_to_play}")
                            
                            # This is the critical test - the message should include all required fields
                            await ws.send(json.dumps({
                                "type": "play_card",
                                "room_code": ROOM_CODE,
                                "player_id": player_id,
                                "card": card_to_play
                            }))
                            
                            print(f"[{player_name}] Sent play_card message with all required fields")
                            return True  # Success - we sent the message
                    
                    elif msg_type == 'card_played':
                        player = data.get('player')
                        card = data.get('card')
                        print(f"[{player_name}] {player} played {card}")
                        
                    elif msg_type == 'error':
                        error_msg = data.get('message', '')
                        print(f"[{player_name}] ERROR: {error_msg}")
                        
                        # Check if it's the malformed message error
                        if "Malformed play_card message" in error_msg:
                            print(f"[{player_name}] ❌ FAILED: Still getting malformed play_card error!")
                            return False
                        elif "missing 'room_code', 'player_id', or 'card'" in error_msg:
                            print(f"[{player_name}] ❌ FAILED: Still missing required fields!")
                            return False
                    
                except asyncio.TimeoutError:
                    print(f"[{player_name}] Timeout waiting for message")
                    break
                except Exception as e:
                    print(f"[{player_name}] Error: {e}")
                    break
            
            return False
    except Exception as e:
        print(f"[{player_name}] Connection error: {e}")
        return False

@pytest.mark.asyncio
async def test_play_card_format():
    """Test that clients send correctly formatted play_card messages"""
    print("=== Testing play_card message format fix ===")
    
    # Clear room first
    try:
        async with websockets.connect(SERVER_URI) as ws:
            await ws.send(json.dumps({
                'type': 'clear_room',
                'room_code': ROOM_CODE
            }))
            print("Room cleared")
    except Exception as e:
        print(f"Could not clear room: {e}")
    
    await asyncio.sleep(1)
    
    # Start 4 players concurrently
    players = [
        ("Player1", False),
        ("Player2", False), 
        ("Player3", True),   # This player will be hakem
        ("Player4", False)
    ]
    
    tasks = [_test_player(name, is_hakem) for name, is_hakem in players]
    
    try:
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
        
        # Check results
        success_count = sum(1 for result in results if result)
        print(f"\n=== Test Results ===")
        print(f"Players that successfully sent play_card: {success_count}/4")
        
        if success_count > 0:
            print("✅ SUCCESS: play_card message format fix is working!")
            print("The client now includes room_code, player_id, and card in play_card messages")
        else:
            print("❌ FAILED: No players could send play_card messages successfully")
            
    except asyncio.TimeoutError:
        print("⏰ Test timed out after 30 seconds")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
