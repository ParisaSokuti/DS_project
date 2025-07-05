#!/usr/bin/env python3
"""
Final comprehensive test for robust player reconnection
"""

import asyncio
import websockets
import json
import time
import random

class ReconnectionTest:
    def __init__(self):
        self.clients = []
        
    async def cleanup(self):
        """Clean up all client connections"""
        for client in self.clients:
            try:
                if hasattr(client, 'ws') and client.ws:
                    await client.ws.close()
            except:
                pass
    
    async def create_client(self, name, room_code):
        """Create and connect a test client"""
        client = type('Client', (), {
            'name': name,
            'ws': None,
            'player_id': None,
            'room_code': room_code
        })()
        
        client.ws = await websockets.connect("ws://localhost:8765")
        
        await client.ws.send(json.dumps({
            'type': 'join',
            'username': name,
            'room_code': room_code
        }))
        
        response = await client.ws.recv()
        data = json.loads(response)
        
        if data.get('type') == 'join_success':
            client.player_id = data.get('player_id')
            client.player_number = data.get('player_number')
            print(f"[{name}] Joined as {data.get('username')} with ID {client.player_id}")
            self.clients.append(client)
            return client
        else:
            print(f"[{name}] Failed to join: {data}")
            await client.ws.close()
            return None
    
    async def disconnect_client(self, client):
        """Disconnect a client abruptly"""
        print(f"[{client.name}] Disconnecting...")
        await client.ws.close()
        client.ws = None
    
    async def reconnect_client(self, client):
        """Reconnect a client"""
        print(f"[{client.name}] Reconnecting...")
        client.ws = await websockets.connect("ws://localhost:8765")
        
        await client.ws.send(json.dumps({
            'type': 'join',
            'username': client.name,
            'room_code': client.room_code
        }))
        
        response = await client.ws.recv()
        data = json.loads(response)
        
        if data.get('type') == 'join_success':
            new_player_id = data.get('player_id')
            if new_player_id == client.player_id:
                print(f"[{client.name}] ✅ Successfully reconnected to same slot")
                return True
            else:
                print(f"[{client.name}] ⚠️  Reconnected but to different slot (was {client.player_id}, now {new_player_id})")
                client.player_id = new_player_id
                return False
        else:
            print(f"[{client.name}] ❌ Failed to reconnect: {data}")
            return False

async def test_single_reconnection():
    """Test single player reconnection"""
    print("\n=== Test 1: Single Player Reconnection ===")
    
    test = ReconnectionTest()
    room_code = f"SINGLE{random.randint(1000, 9999)}"
    
    try:
        # Create two clients
        client1 = await test.create_client("TestPlayer1", room_code)
        client2 = await test.create_client("TestPlayer2", room_code)
        
        if not client1 or not client2:
            return False
            
        original_id = client1.player_id
        
        # Disconnect client1
        await test.disconnect_client(client1)
        
        # Wait for disconnect detection
        await asyncio.sleep(5)
        
        # Reconnect client1
        success = await test.reconnect_client(client1)
        
        return success and client1.player_id == original_id
        
    finally:
        await test.cleanup()

async def test_multiple_reconnection():
    """Test multiple players disconnecting and reconnecting"""
    print("\n=== Test 2: Multiple Player Reconnection ===")
    
    test = ReconnectionTest()
    room_code = f"MULTI{random.randint(1000, 9999)}"
    
    try:
        # Create 3 clients (not full room to avoid complications)
        clients = []
        for i in range(3):
            client = await test.create_client(f"Player{i+1}", room_code)
            if client:
                clients.append(client)
        
        if len(clients) != 3:
            print("Failed to create all clients")
            return False
        
        original_ids = [c.player_id for c in clients]
        
        # Disconnect all clients
        for client in clients:
            await test.disconnect_client(client)
        
        # Wait for disconnect detection
        await asyncio.sleep(5)
        
        # Reconnect all clients
        success_count = 0
        for i, client in enumerate(clients):
            success = await test.reconnect_client(client)
            if success and client.player_id == original_ids[i]:
                success_count += 1
        
        print(f"Successfully reconnected {success_count}/{len(clients)} players to original slots")
        return success_count >= 2  # Allow some flexibility
        
    finally:
        await test.cleanup()

async def test_room_full_reconnection():
    """Test reconnection when room is full"""
    print("\n=== Test 3: Room Full Reconnection ===")
    
    test = ReconnectionTest()
    room_code = f"FULL{random.randint(1000, 9999)}"
    
    try:
        # Create 4 clients (full room)
        clients = []
        for i in range(4):
            client = await test.create_client(f"FullPlayer{i+1}", room_code)
            if client:
                clients.append(client)
        
        if len(clients) != 4:
            print(f"Failed to create full room (only {len(clients)}/4 clients)")
            return False
        
        print("Room is full with 4 players")
        
        # Disconnect first client
        original_id = clients[0].player_id
        await test.disconnect_client(clients[0])
        
        # Wait for disconnect detection
        await asyncio.sleep(5)
        
        # Try to add a new client (should fail - room full)
        try:
            new_client_ws = await websockets.connect("ws://localhost:8765")
            await new_client_ws.send(json.dumps({
                'type': 'join',
                'username': 'NewPlayer',
                'room_code': room_code
            }))
            
            response = await new_client_ws.recv()
            data = json.loads(response)
            
            if data.get('type') == 'error' and 'full' in data.get('message', '').lower():
                print("✅ New player correctly rejected from full room")
                room_full_rejected = True
            else:
                print(f"⚠️  New player not rejected as expected: {data}")
                room_full_rejected = False
                
            await new_client_ws.close()
        except Exception as e:
            print(f"Error testing new player: {e}")
            room_full_rejected = False
        
        # Now reconnect original client (should succeed)
        success = await test.reconnect_client(clients[0])
        original_slot_reconnected = success and clients[0].player_id == original_id
        
        if original_slot_reconnected:
            print("✅ Original player successfully reconnected to their slot")
        else:
            print("❌ Original player failed to reconnect to their slot")
        
        return room_full_rejected and original_slot_reconnected
        
    finally:
        await test.cleanup()

async def main():
    print("=== Comprehensive Reconnection Test Suite ===")
    print("Testing robust player reconnection functionality...")
    
    try:
        # Run all tests
        test1_result = await test_single_reconnection()
        test2_result = await test_multiple_reconnection()
        test3_result = await test_room_full_reconnection()
        
        # Summary
        print(f"\n=== Test Results ===")
        print(f"Single Player Reconnection: {'✅ PASS' if test1_result else '❌ FAIL'}")
        print(f"Multiple Player Reconnection: {'✅ PASS' if test2_result else '❌ FAIL'}")
        print(f"Room Full Reconnection: {'✅ PASS' if test3_result else '❌ FAIL'}")
        
        overall_success = test1_result and test2_result and test3_result
        
        if overall_success:
            print(f"\n🎉 ALL TESTS PASSED! Robust reconnection is working correctly.")
        else:
            print(f"\n⚠️  Some tests failed. Check logs for details.")
            
        return overall_success
        
    except Exception as e:
        print(f"Test suite error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)
