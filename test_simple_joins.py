#!/usr/bin/env python3

import asyncio
import websockets
import json
import time
import uuid

async def test_simple_player_joins():
    """Test basic player joins to verify Redis fix"""
    
    # Use the existing client authentication system
    connections = []
    room_code = "9999"
    players = ["arvin", "parisa", "kasra", "nima"]
    
    print("🧪 Testing simple player joins...")
    print(f"📦 Room code: {room_code}")
    
    try:
        for i, username in enumerate(players):
            print(f"\n👤 Adding player {i+1}: {username}")
            
            # Connect to server  
            uri = "ws://localhost:8765"
            websocket = await websockets.connect(uri)
            connections.append(websocket)
            
            # Use simple registration
            auth_message = {
                "type": "auth_register",
                "username": username,
                "password": "testpass123",
                "display_name": f"{username.title()} Player"
            }
            
            await websocket.send(json.dumps(auth_message))
            
            # Wait for auth response
            try:
                auth_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"   🔐 Auth response: {auth_response}")
                
                auth_data = json.loads(auth_response)
                if not auth_data.get('success', False):
                    print(f"   ❌ Authentication failed: {auth_data.get('message', 'Unknown error')}")
                    continue
                    
            except asyncio.TimeoutError:
                print(f"   ⚠️  Auth timeout for {username}")
                continue
            
            # Join room
            join_message = {
                "type": "join",
                "room_code": room_code
            }
            
            await websocket.send(json.dumps(join_message))
            
            # Wait for join response
            try:
                join_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"   🚪 Join response: {join_response}")
            except asyncio.TimeoutError:
                print(f"   ⚠️  Join timeout for {username}")
            
            # Small delay between players
            await asyncio.sleep(1.0)
        
        print(f"\n✅ All players processed!")
        
        # Wait for any game start messages
        print(f"\n⏳ Waiting for game start messages...")
        await asyncio.sleep(3.0)
        
        # Check for additional messages
        for i, ws in enumerate(connections):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    print(f"   Player {i+1} received: {message}")
            except asyncio.TimeoutError:
                print(f"   Player {i+1}: No more messages")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up connections
        print(f"\n🧹 Cleaning up connections...")
        for ws in connections:
            try:
                await ws.close()
            except:
                pass
        
        print(f"✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_simple_player_joins())
