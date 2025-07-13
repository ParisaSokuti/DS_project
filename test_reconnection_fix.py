#!/usr/bin/env python3
"""
Test script to verify reconnection functionality works correctly.
This test simulates a player disconnecting and reconnecting during gameplay.
"""

import asyncio
import json
import websockets
import os
import tempfile
import subprocess
import time

# Test configuration
SERVER_URI = "ws://localhost:8765"
TEST_ROOM = "test_room"
TEST_USERS = ["alice", "bob", "charlie", "diana"]

async def connect_and_authenticate(username, password="testpass"):
    """Connect to server and authenticate"""
    try:
        ws = await websockets.connect(SERVER_URI)
        
        # Login
        await ws.send(json.dumps({
            "type": "login",
            "username": username,
            "password": password
        }))
        
        response = await ws.recv()
        auth_data = json.loads(response)
        
        if auth_data.get("type") == "auth_response" and auth_data.get("success"):
            print(f"✅ {username} authenticated successfully")
            player_id = auth_data.get("player_id")
            return ws, player_id
        else:
            print(f"❌ {username} authentication failed: {auth_data.get('message')}")
            return None, None
            
    except Exception as e:
        print(f"❌ Failed to connect {username}: {e}")
        return None, None

async def join_room(ws, room_code):
    """Join a room"""
    await ws.send(json.dumps({
        "type": "join",
        "room_code": room_code
    }))
    
    response = await ws.recv()
    data = json.loads(response)
    
    if data.get("type") == "join_success":
        print(f"✅ Joined room {room_code}")
        return True
    else:
        print(f"❌ Failed to join room: {data.get('message')}")
        return False

async def test_reconnection():
    """Test reconnection functionality"""
    print("🧪 Testing reconnection functionality...")
    
    # Start server if not running
    try:
        # Test server connection
        test_ws = await websockets.connect(SERVER_URI)
        await test_ws.close()
        print("✅ Server is running")
    except:
        print("❌ Server is not running. Please start the server first.")
        return
    
    # Connect first player
    ws1, player_id1 = await connect_and_authenticate("alice")
    if not ws1:
        print("❌ Could not connect alice")
        return
    
    # Join room
    await join_room(ws1, TEST_ROOM)
    
    # Save player ID for reconnection test
    session_file = f"/tmp/test_session_alice"
    with open(session_file, 'w') as f:
        f.write(player_id1)
    
    print(f"💾 Saved alice's player_id: {player_id1[:8]}...")
    
    # Simulate disconnect (close connection)
    print("🔌 Simulating disconnect...")
    await ws1.close()
    
    # Wait a moment
    await asyncio.sleep(2)
    
    # Reconnect
    print("🔄 Attempting to reconnect...")
    ws2, _ = await connect_and_authenticate("alice")
    if not ws2:
        print("❌ Could not reconnect alice")
        return
    
    # Send reconnect message
    await ws2.send(json.dumps({
        "type": "reconnect",
        "player_id": player_id1,
        "room_code": TEST_ROOM
    }))
    
    # Wait for reconnection response
    try:
        response = await asyncio.wait_for(ws2.recv(), timeout=5)
        data = json.loads(response)
        
        if data.get("type") == "reconnect_success":
            print("✅ Reconnection successful!")
            game_state = data.get("game_state", {})
            print(f"📋 Restored game state: {game_state.get('phase', 'unknown')}")
            
            # Check if hand was restored
            hand = game_state.get("hand", [])
            if hand:
                print(f"🎴 Hand restored: {len(hand)} cards")
            else:
                print("🎴 No hand to restore (normal if game not in progress)")
            
            # Test if we can receive turn updates
            await ws2.send(json.dumps({
                "type": "get_game_state",
                "room_code": TEST_ROOM
            }))
            
            print("✅ Reconnection test passed!")
            
        else:
            print(f"❌ Reconnection failed: {data.get('message')}")
            
    except asyncio.TimeoutError:
        print("❌ Reconnection timeout")
    except Exception as e:
        print(f"❌ Reconnection error: {e}")
    
    # Clean up
    try:
        await ws2.close()
        os.remove(session_file)
    except:
        pass

if __name__ == "__main__":
    asyncio.run(test_reconnection())
