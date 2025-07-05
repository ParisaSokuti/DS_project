#!/usr/bin/env python3
"""
Debug script to check if players are correctly stored in Redis room data
"""

import asyncio
import websockets
import json
import time
import sys
import uuid

async def test_redis_room_storage():
    """Test if players are correctly stored and retrieved from Redis"""
    
    # Generate unique identifiers
    room_code = f"REDIS{int(time.time()) % 10000}"
    
    print(f"=== TESTING REDIS ROOM STORAGE ===")
    print(f"Room Code: {room_code}")
    print()
    
    try:
        # Step 1: Connect one player and check Redis storage
        print("Step 1: Connecting first player...")
        
        player_id = str(uuid.uuid4())
        username = "TestPlayer1"
        
        ws = await websockets.connect("ws://localhost:8765")
        join_msg = {
            "type": "join",
            "room_code": room_code,
            "username": username,
            "player_id": player_id
        }
        
        await ws.send(json.dumps(join_msg))
        response = json.loads(await ws.recv())
        print(f"Join response: {response}")
        
        if response.get('type') != 'join_success':
            print("Failed to join room")
            return
        
        actual_player_id = response.get('player_id')
        print(f"Server assigned player_id: {actual_player_id}")
        
        # Step 2: Try to query Redis directly by sending a special message
        # (We need to implement this in the server, but for now let's disconnect and reconnect)
        
        print("\nStep 2: Disconnecting and immediately trying to reconnect...")
        await ws.close()
        
        # Wait briefly
        await asyncio.sleep(0.1)
        
        # Try to reconnect immediately
        ws_new = await websockets.connect("ws://localhost:8765")
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": actual_player_id
        }
        
        await ws_new.send(json.dumps(reconnect_msg))
        
        try:
            reconnect_response = json.loads(await asyncio.wait_for(ws_new.recv(), timeout=3.0))
            print(f"Immediate reconnect response: {reconnect_response}")
            
            if reconnect_response.get('type') == 'error':
                if 'not found' in reconnect_response.get('message', '').lower():
                    print("❌ Player was removed from room immediately on disconnect")
                    print("   This suggests the disconnect handling is removing players instead of marking them disconnected")
                else:
                    print(f"❌ Other error: {reconnect_response.get('message')}")
            else:
                print("✓ Player was found in room - disconnect handling working correctly")
                
        except asyncio.TimeoutError:
            print("❌ TIMEOUT: No response to immediate reconnect")
        
        # Clean up
        try:
            await ws_new.close()
        except:
            pass
        
    except Exception as e:
        print(f"ERROR in test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_redis_room_storage())
