#!/usr/bin/env python3

import asyncio
import websockets
import json
import time
import uuid

async def test_player_count_fix():
    """Test the Redis player count fix by adding 4 players sequentially"""
    
    # Player data for testing
    players = [
        {"username": "arvin", "display_name": "Arvin Player"},
        {"username": "parisa", "display_name": "Parisa Player"},
        {"username": "kasra", "display_name": "Kasra Player"},
        {"username": "nima", "display_name": "Nima Player"}
    ]
    
    connections = []
    room_code = "9999"
    
    print("🧪 Testing Redis player count fix...")
    print(f"📦 Room code: {room_code}")
    print(f"👥 Adding {len(players)} players sequentially...")
    
    try:
        # Connect and authenticate each player
        for i, player in enumerate(players):
            print(f"\n👤 Adding player {i+1}: {player['username']}")
            
            # Connect to server
            uri = "ws://localhost:8765"
            websocket = await websockets.connect(uri)
            connections.append(websocket)
            
            # Generate unique player ID
            player_id = str(uuid.uuid4())
            
            # Authenticate (simplified)
            auth_message = {
                "type": "auth",
                "username": player["username"],
                "display_name": player["display_name"],
                "player_id": player_id
            }
            
            await websocket.send(json.dumps(auth_message))
            
            # Wait for auth response
            try:
                auth_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"   🔐 Auth response: {auth_response}")
            except asyncio.TimeoutError:
                print(f"   ⚠️  Auth timeout")
            
            # Join room
            join_message = {
                "type": "join",
                "room_code": room_code,
                "username": player["username"],
                "display_name": player["display_name"]
            }
            
            await websocket.send(json.dumps(join_message))
            
            # Wait for join response
            try:
                join_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"   🚪 Join response: {join_response}")
            except asyncio.TimeoutError:
                print(f"   ⚠️  Join timeout")
            
            # Small delay between players
            await asyncio.sleep(0.5)
        
        print(f"\n✅ All {len(players)} players added!")
        
        # Check Redis state
        print("\n🔍 Checking Redis state...")
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        
        players_key = f"room:{room_code}:players"
        print(f"   📋 Players key exists: {r.exists(players_key)}")
        print(f"   📊 Players list length: {r.llen(players_key)}")
        
        # Get all players
        players_data = r.lrange(players_key, 0, -1)
        print(f"   👥 Players in Redis:")
        for i, player_data in enumerate(players_data):
            try:
                player = json.loads(player_data.decode())
                print(f"      {i+1}. {player.get('username', 'unknown')} (ID: {player.get('player_id', 'unknown')[:8]}...)")
            except Exception as e:
                print(f"      {i+1}. Error decoding: {e}")
        
        # Wait for potential game start
        print(f"\n⏳ Waiting for game to start...")
        await asyncio.sleep(2.0)
        
        # Check for game start messages
        print(f"\n📨 Checking for game start messages...")
        for i, ws in enumerate(connections):
            try:
                # Check if there are any pending messages
                message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                print(f"   Player {i+1} received: {message}")
            except asyncio.TimeoutError:
                print(f"   Player {i+1}: No message received")
        
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
    asyncio.run(test_player_count_fix())
