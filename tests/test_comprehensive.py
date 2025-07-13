#!/usr/bin/env python3
"""
Final comprehensive test: Multiple clients + reconnection
"""

import asyncio
import websockets
import json
import time

SERVER_URI = "ws://localhost:8765"

async def test_client(client_name, action="join", player_id=None):
    """Test client with different actions"""
    try:
        async with websockets.connect(SERVER_URI) as ws:
            if action == "join":
                message = {"type": "join", "username": client_name, "room_code": "9999"}
            elif action == "reconnect":
                message = {"type": "reconnect", "player_id": player_id, "room_code": "9999"}
            
            await ws.send(json.dumps(message))
            
            response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = json.loads(response_raw)
            
            if response.get('type') in ['join_success', 'reconnect_success']:
                return {
                    'username': response.get('username'),
                    'player_id': response.get('player_id'),
                    'player_number': response.get('player_number'),
                    'reconnected': response.get('reconnected', False),
                    'success': True
                }
            else:
                return {'success': False, 'error': response}
                
    except Exception as e:
        return {'success': False, 'error': str(e)}

async def main():
    """Comprehensive test sequence"""
    print("🧪 Comprehensive Test: Multiple Clients + Reconnection")
    
    # Clear Redis first
    import redis
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.flushall()
    print("✅ Redis cleared")
    
    # Step 1: 4 fresh clients join
    print("\n=== Step 1: 4 fresh clients join ===")
    original_clients = []
    for i in range(1, 5):
        result = await test_client(f"Client{i}")
        if result['success']:
            original_clients.append(result)
            print(f"✅ {result['username']}: Player {result['player_number']} ({result['player_id'][:8]}...)")
        else:
            print(f"❌ Client{i}: {result['error']}")
    
    print(f"Connected clients: {len(original_clients)}")
    
    # Step 2: Simulate disconnection (just wait for server to detect)
    print(f"\n=== Step 2: Wait for disconnect detection ===")
    await asyncio.sleep(5)  # Wait for disconnect detection
    
    # Step 3: Try to join new client (should be rejected - room full)
    print(f"\n=== Step 3: New client tries to join (should be rejected) ===")
    new_client_result = await test_client("NewClient")
    if new_client_result['success']:
        print(f"❌ UNEXPECTED: NewClient joined as {new_client_result['username']}")
    else:
        print(f"✅ EXPECTED: NewClient rejected - {new_client_result['error']}")
    
    # Step 4: Original client reconnects
    print(f"\n=== Step 4: Original client reconnects ===")
    if original_clients:
        original_player_id = original_clients[0]['player_id']
        reconnect_result = await test_client("ReconnectingClient", "reconnect", original_player_id)
        if reconnect_result['success']:
            print(f"✅ Reconnection successful: {reconnect_result['username']} (Player {reconnect_result['player_number']})")
            print(f"   Original ID: {original_player_id[:8]}...")
            print(f"   Reconnected ID: {reconnect_result['player_id'][:8]}...")
            if original_player_id == reconnect_result['player_id']:
                print("   ✅ Same player ID - correct!")
            else:
                print("   ❌ Different player ID - error!")
        else:
            print(f"❌ Reconnection failed: {reconnect_result['error']}")
    
    print(f"\n📊 Test completed!")

if __name__ == "__main__":
    asyncio.run(main())
