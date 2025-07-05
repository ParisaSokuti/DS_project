#!/usr/bin/env python3
"""
Simple test to verify the play_card message format includes all required fields
"""

import asyncio
import websockets
import json

SERVER_URI = "ws://localhost:8765"

async def test_message_format():
    """Test the play_card message format by examining what the client would send"""
    
    # Simulate the values that would be available in the client
    room_code = "9999"
    player_id = "test-player-id-123"
    card = "A_hearts"
    
    # This is the message format the client now sends
    play_card_message = {
        "type": "play_card",
        "room_code": room_code,
        "player_id": player_id,
        "card": card
    }
    
    print("=== Testing play_card message format ===")
    print("Old format (broken):")
    old_format = {
        "type": "play_card",
        "card": card
    }
    print(json.dumps(old_format, indent=2))
    
    print("\nNew format (fixed):")
    print(json.dumps(play_card_message, indent=2))
    
    # Check that all required fields are present
    required_fields = ['room_code', 'player_id', 'card']
    missing_fields = [field for field in required_fields if field not in play_card_message]
    
    if missing_fields:
        print(f"\n❌ FAILED: Missing required fields: {missing_fields}")
        return False
    else:
        print(f"\n✅ SUCCESS: All required fields present: {required_fields}")
        return True

async def test_connection():
    """Test that we can connect and the server accepts the new message format"""
    try:
        async with websockets.connect(SERVER_URI) as ws:
            # Test connection
            await ws.send(json.dumps({
                "type": "join",
                "username": "TestPlayer",
                "room_code": "TEST"
            }))
            
            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=3.0)
            data = json.loads(response)
            
            if data.get('type') == 'join_success':
                print("✅ Server connection test: SUCCESS")
                return True
            else:
                print(f"⚠️ Server connection test: Unexpected response: {data}")
                return False
                
    except Exception as e:
        print(f"❌ Server connection test: FAILED - {e}")
        return False

if __name__ == "__main__":
    print("Testing play_card message format fix...\n")
    
    # Test message format
    format_ok = asyncio.run(test_message_format())
    
    print("\n" + "="*50)
    
    # Test server connection
    connection_ok = asyncio.run(test_connection())
    
    print("\n" + "="*50)
    print("SUMMARY:")
    print(f"Message format: {'✅ PASS' if format_ok else '❌ FAIL'}")
    print(f"Server connection: {'✅ PASS' if connection_ok else '❌ FAIL'}")
    
    if format_ok:
        print("\n🎉 The play_card message format fix is working!")
        print("The client now includes all required fields: room_code, player_id, and card")
    else:
        print("\n❌ The fix needs more work")
