#!/usr/bin/env python3
"""
Simple test to check if the reconnection issue is related to existing sessions.
"""

import asyncio
import json
import websockets

async def test_simple_login():
    """Test simple login without existing sessions"""
    
    print("🧪 Testing Simple Login")
    print("=" * 30)
    
    try:
        print("🔌 Connecting...")
        ws = await websockets.connect("ws://localhost:8765")
        
        # Try registering a new user to test authentication
        register_message = {
            "type": "auth_register",
            "username": "testuser123",
            "password": "testpass123",
            "email": "test@test.com",
            "display_name": "Test User"
        }
        
        print("🔐 Registering new user...")
        await ws.send(json.dumps(register_message))
        
        # Wait for response
        response = await asyncio.wait_for(ws.recv(), timeout=10)
        data = json.loads(response)
        
        print(f"📨 Response: {data}")
        
        if data.get("success"):
            print("✅ Registration successful!")
            player_info = data.get("player_info", {})
            player_id = player_info.get("player_id")
            username = player_info.get("username")
            
            print(f"   Player: {username}")
            print(f"   Player ID: {player_id}")
            
            # Try to join a room
            print("🏠 Joining room...")
            join_message = {
                "type": "join",
                "room_code": "test_room"
            }
            
            await ws.send(json.dumps(join_message))
            
            # Wait for join response
            join_response = await asyncio.wait_for(ws.recv(), timeout=10)
            join_data = json.loads(join_response)
            
            print(f"📨 Join response: {join_data}")
            
            if join_data.get("type") == "join_success":
                print("✅ Successfully joined room!")
                
                # Simulate disconnect
                print("🔌 Disconnecting...")
                await ws.close()
                
                # Wait a moment
                await asyncio.sleep(2)
                
                # Test reconnection
                print("🔄 Testing reconnection...")
                ws2 = await websockets.connect("ws://localhost:8765")
                
                # Re-authenticate with same credentials
                login_message = {
                    "type": "auth_login",
                    "username": "testuser123",
                    "password": "testpass123"
                }
                
                print("🔐 Re-authenticating...")
                await ws2.send(json.dumps(login_message))
                
                auth_response = await asyncio.wait_for(ws2.recv(), timeout=10)
                auth_data = json.loads(auth_response)
                
                print(f"📨 Auth response: {auth_data}")
                
                if auth_data.get("success"):
                    print("✅ Re-authentication successful!")
                    
                    # Try to reconnect to game
                    reconnect_message = {
                        "type": "reconnect",
                        "player_id": player_id,
                        "room_code": "test_room"
                    }
                    
                    print("🔄 Attempting game reconnection...")
                    await ws2.send(json.dumps(reconnect_message))
                    
                    # Wait for response
                    reconnect_response = await asyncio.wait_for(ws2.recv(), timeout=10)
                    reconnect_data = json.loads(reconnect_response)
                    
                    print(f"📨 Reconnect response: {reconnect_data}")
                    
                    if reconnect_data.get("type") == "reconnect_success":
                        print("✅ RECONNECTION SUCCESSFUL!")
                    elif reconnect_data.get("type") == "error":
                        print(f"❌ Reconnection failed: {reconnect_data.get('message')}")
                    else:
                        print(f"❓ Unexpected response: {reconnect_data}")
                else:
                    print(f"❌ Re-authentication failed: {auth_data.get('message')}")
                
                # Clean up
                await ws2.close()
            else:
                print(f"❌ Failed to join room: {join_data}")
        else:
            print(f"❌ Registration failed: {data.get('message')}")
            
        await ws.close()
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_simple_login())
