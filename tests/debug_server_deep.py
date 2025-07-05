#!/usr/bin/env python3
"""
Targeted Server Debugging - Deep Investigation

This script performs targeted debugging to understand server issues.
"""

import asyncio
import websockets
import json
import time
import redis

async def debug_room_joining():
    """Debug room joining specifically"""
    print("🔍 Deep Debugging Room Joining...")
    
    # Check Redis state first
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    print("\n📊 Redis State Before Test:")
    all_keys = redis_client.keys("*")
    print(f"Total Redis keys: {len(all_keys)}")
    
    room_keys = [key for key in all_keys if "9999" in key]
    print(f"Room 9999 keys: {room_keys}")
    
    for key in room_keys:
        key_type = redis_client.type(key)
        if key_type == 'hash':
            data = redis_client.hgetall(key)
            print(f"  {key} (hash): {data}")
        elif key_type == 'list':
            data = redis_client.lrange(key, 0, -1)
            print(f"  {key} (list): {data}")
        elif key_type == 'string':
            data = redis_client.get(key)
            print(f"  {key} (string): {data}")
    
    print("\n🔗 Testing Single Client Join:")
    try:
        ws = await websockets.connect("ws://localhost:8765")
        print("✅ Connected to server")
        
        join_msg = {'type': 'join', 'room_code': '9999'}
        await ws.send(json.dumps(join_msg))
        print(f"📤 Sent: {join_msg}")
        
        # Wait for response
        response = await asyncio.wait_for(ws.recv(), timeout=10.0)
        response_data = json.loads(response)
        print(f"📥 Received: {response_data}")
        
        # Check Redis state after join
        print("\n📊 Redis State After Join:")
        room_keys_after = [key for key in redis_client.keys("*") if "9999" in key or "session:" in key]
        print(f"Relevant keys: {room_keys_after}")
        
        for key in room_keys_after:
            key_type = redis_client.type(key)
            if key_type == 'hash':
                data = redis_client.hgetall(key)
                print(f"  {key} (hash): {data}")
            elif key_type == 'list':
                data = redis_client.lrange(key, 0, -1)
                print(f"  {key} (list): {data}")
        
        # Try to join 3 more clients
        print(f"\n🔗 Testing Additional Clients:")
        additional_clients = []
        
        for i in range(3):
            try:
                ws_extra = await websockets.connect("ws://localhost:8765")
                join_msg_extra = {'type': 'join', 'room_code': '9999'}
                await ws_extra.send(json.dumps(join_msg_extra))
                
                response_extra = await asyncio.wait_for(ws_extra.recv(), timeout=5.0)
                response_data_extra = json.loads(response_extra)
                print(f"📥 Client {i+2}: {response_data_extra}")
                
                additional_clients.append(ws_extra)
                
            except Exception as e:
                print(f"❌ Client {i+2} failed: {e}")
        
        # Wait a bit to see if game starts
        print(f"\n⏰ Waiting for game start messages...")
        try:
            # Try to receive more messages
            for i in range(5):
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(msg)
                print(f"📥 Additional message: {data}")
        except asyncio.TimeoutError:
            print("⏰ No additional messages received")
        
        # Close connections
        await ws.close()
        for client in additional_clients:
            try:
                await client.close()
            except:
                pass
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

async def debug_server_active_games():
    """Check what games the server thinks are active"""
    print("\n🎮 Checking Server Active Games...")
    
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # Look for game state keys
    game_keys = redis_client.keys("room:*:game_state")
    print(f"Found {len(game_keys)} game state keys:")
    
    for key in game_keys:
        room_code = key.split(':')[1]
        game_state = redis_client.hgetall(key)
        print(f"  Room {room_code}:")
        print(f"    Phase: {game_state.get('phase', 'unknown')}")
        print(f"    Players: {game_state.get('players', 'none')}")
        print(f"    Hakem: {game_state.get('hakem', 'none')}")
    
    # Look for room player lists
    room_keys = redis_client.keys("room:*:players")
    print(f"\nFound {len(room_keys)} room player lists:")
    
    for key in room_keys:
        room_code = key.split(':')[1]
        players = redis_client.lrange(key, 0, -1)
        print(f"  Room {room_code}: {len(players)} players")
        for i, player_data in enumerate(players):
            try:
                player_info = json.loads(player_data)
                print(f"    Player {i+1}: {player_info.get('username', 'unknown')} ({player_info.get('connection_status', 'unknown')})")
            except:
                print(f"    Player {i+1}: {player_data}")

async def main():
    print("🔍 TARGETED SERVER DEBUGGING")
    print("="*50)
    
    await debug_server_active_games()
    await debug_room_joining()
    
    print("\n" + "="*50)
    print("🎯 DEBUGGING COMPLETE")

if __name__ == "__main__":
    asyncio.run(main())
