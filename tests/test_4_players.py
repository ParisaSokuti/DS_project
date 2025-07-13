#!/usr/bin/env python3
"""
Test script to replicate the exact user issue: 4 players all seeing the same connection
"""

import asyncio
import websockets
import json
import time

SERVER_URI = "ws://localhost:8765"

async def start_client(client_id):
    """Start a client that behaves like the real client"""
    print(f"\n=== Client {client_id} ===")
    
    try:
        async with websockets.connect(SERVER_URI) as ws:
            # Send join message (like a fresh client)
            message = {
                "type": "join",
                "username": f"Player{client_id}",
                "room_code": "9999"
            }
            
            await ws.send(json.dumps(message))
            
            # Wait for response
            response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = json.loads(response_raw)
            
            if response.get('type') == 'join_success':
                username = response.get('username')
                player_id = response.get('player_id')
                player_number = response.get('player_number')
                reconnected = response.get('reconnected', False)
                
                print(f"Client {client_id} connected:")
                print(f"  Username: {username}")
                print(f"  Player Number: {player_number}")
                print(f"  Player ID: {player_id[:8]}...")
                print(f"  Reconnected: {reconnected}")
                
                # Wait a bit to see game state
                try:
                    state_msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    state = json.loads(state_msg)
                    if state.get('type') == 'game_state':
                        print(f"  Game state: {state.get('data', {}).get('phase', 'unknown')}")
                except asyncio.TimeoutError:
                    print("  No additional game state received")
                
                return {
                    'client_id': client_id,
                    'username': username,
                    'player_id': player_id,
                    'player_number': player_number,
                    'reconnected': reconnected
                }
            else:
                print(f"Client {client_id} failed: {response}")
                return None
                
    except Exception as e:
        print(f"Client {client_id} error: {e}")
        return None

async def main():
    """Test 4 clients connecting simultaneously"""
    print("🧪 Testing 4 clients connecting to replicate user issue")
    
    # Start 4 clients concurrently
    tasks = []
    for i in range(1, 5):
        task = asyncio.create_task(start_client(i))
        tasks.append(task)
        # Small delay between starts
        await asyncio.sleep(0.5)
    
    # Wait for all clients to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    print(f"\n📊 Results Summary:")
    unique_player_ids = set()
    unique_usernames = set()
    unique_player_numbers = set()
    
    for i, result in enumerate(results):
        if isinstance(result, dict):
            print(f"  Client {i+1}: {result['username']} (Player {result['player_number']}) - {result['player_id'][:8]}...")
            unique_player_ids.add(result['player_id'])
            unique_usernames.add(result['username'])
            unique_player_numbers.add(result['player_number'])
        else:
            print(f"  Client {i+1}: Failed - {result}")
    
    print(f"\n✅ Analysis:")
    print(f"  Unique Player IDs: {len(unique_player_ids)} (should be 4)")
    print(f"  Unique Usernames: {len(unique_usernames)} (should be 4)")
    print(f"  Unique Player Numbers: {len(unique_player_numbers)} (should be 4)")
    
    if len(unique_player_ids) == 4:
        print("  ✅ SUCCESS: All clients got unique player IDs!")
    else:
        print("  ❌ FAILURE: Some clients got duplicate player IDs")
    
    if len(unique_player_numbers) == 4:
        print("  ✅ SUCCESS: All clients got unique player numbers!")
    else:
        print("  ❌ FAILURE: Some clients got duplicate player numbers")

if __name__ == "__main__":
    asyncio.run(main())
