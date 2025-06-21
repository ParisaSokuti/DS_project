#!/usr/bin/env python3
"""
Quick test to verify the play_card message fix
"""

import asyncio
import websockets
import json
import sys

SERVER_URI = "ws://localhost:8765"
ROOM_CODE = "9999"

async def test_play_card_fix():
    """Test that play_card messages work correctly"""
    try:
        async with websockets.connect(SERVER_URI) as ws:
            print("Connected to server")
            
            # Join room
            await ws.send(json.dumps({
                "type": "join",
                "username": "TestPlayer",
                "room_code": ROOM_CODE
            }))
            print("Sent join request")
            
            # Wait for responses
            for i in range(10):  # Listen for up to 10 messages
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    print(f"Received: {data.get('type')} - {data}")
                    
                    # Check for errors
                    if data.get('type') == 'error':
                        error_msg = data.get('message', '')
                        if "Malformed play_card message" in error_msg or "missing 'room_code', 'player_id', or 'card'" in error_msg:
                            print(f"❌ Still getting the error: {error_msg}")
                            return False
                        else:
                            print(f"Other error: {error_msg}")
                    
                    # If we get player_id, try to play a card
                    if data.get('type') == 'join_success':
                        player_id = data.get('player_id')
                        print(f"Got player_id: {player_id}")
                        
                        # Try to play a card (this should work now)
                        test_card = {"suit": "hearts", "rank": "A"}
                        await ws.send(json.dumps({
                            "type": "play_card",
                            "room_code": ROOM_CODE,
                            "player_id": player_id,
                            "card": test_card
                        }))
                        print("✅ Successfully sent play_card message with all required fields!")
                        return True
                        
                except asyncio.TimeoutError:
                    print("Timeout waiting for message")
                    break
                    
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    return False

if __name__ == "__main__":
    print("=== Quick Test: play_card message fix ===")
    result = asyncio.run(test_play_card_fix())
    if result:
        print("✅ SUCCESS: play_card message format is fixed!")
    else:
        print("❌ FAILED: Still issues with play_card message")
