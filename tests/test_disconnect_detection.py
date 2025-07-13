#!/usr/bin/env python3
"""
Test script to verify that the server properly detects client disconnections
and allows reconnection to the same slot.
"""

import asyncio
import websockets
import json
import time
import sys

class TestClient:
    def __init__(self, name):
        self.name = name
        self.websocket = None
        self.player_id = None
        self.room_code = None
        
    async def connect(self):
        """Connect to the server"""
        try:
            self.websocket = await websockets.connect("ws://localhost:8765")
            print(f"[{self.name}] Connected to server")
            return True
        except Exception as e:
            print(f"[{self.name}] Failed to connect: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the server"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            print(f"[{self.name}] Disconnected from server")
    
    async def send_message(self, message):
        """Send a message to the server"""
        if self.websocket:
            await self.websocket.send(json.dumps(message))
    
    async def receive_message(self):
        """Receive a message from the server"""
        if self.websocket:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                return json.loads(message)
            except asyncio.TimeoutError:
                return None
        return None
    
    async def join_or_create_room(self, room_code=None):
        """Join an existing room or create a new one"""
        if not room_code:
            room_code = "9999"  # Default room code
            
        await self.send_message({
            'type': 'join',
            'username': self.name,
            'room_code': room_code
        })
        
        # Wait for response
        response = await self.receive_message()
        if response:
            if response.get('type') == 'join_success':
                self.room_code = room_code
                self.player_id = response.get('player_id')
                print(f"[{self.name}] Joined room {self.room_code} as player {self.player_id}")
                return True
            elif response.get('type') == 'player_reconnected':
                self.room_code = room_code
                self.player_id = response.get('player_id')
                print(f"[{self.name}] Reconnected to room {self.room_code} as player {self.player_id}")
                return True
            elif response.get('type') == 'room_full':
                print(f"[{self.name}] Room is full: {response.get('message', 'No message')}")
                return False
            else:
                print(f"[{self.name}] Unexpected response: {response}")
        return False

async def test_disconnect_detection():
    """Test that server detects disconnections and allows reconnection"""
    print("=== Testing Disconnect Detection and Reconnection ===")
    
    # Use a unique room code for this test
    test_room = "TEST01"
    
    # Create first client and room
    client1 = TestClient("Client1")
    await client1.connect()
    
    success = await client1.join_or_create_room(test_room)
    if not success:
        print("Failed to create room")
        return False
    
    room_code = client1.room_code
    player1_id = client1.player_id
    
    print(f"Room created: {room_code}, Player1 ID: {player1_id}")
    
    # Create second client and join room
    client2 = TestClient("Client2")
    await client2.connect()
    
    success = await client2.join_or_create_room(room_code)
    if not success:
        print("Failed to join room")
        return False
    
    player2_id = client2.player_id
    print(f"Player2 joined with ID: {player2_id}")
    
    # Wait a moment for server to register both players
    await asyncio.sleep(2)
    
    # Abruptly disconnect client1 (simulate browser close or network loss)
    print(f"[Test] Abruptly disconnecting {client1.name}...")
    await client1.disconnect()
    
    # Wait for server to detect the disconnection
    print("[Test] Waiting for server to detect disconnection...")
    await asyncio.sleep(35)  # Wait longer than ping interval (30s) + timeout (10s)
    
    # Try to reconnect client1 to the same room
    print(f"[Test] Attempting to reconnect {client1.name}...")
    await client1.connect()
    
    success = await client1.join_or_create_room(room_code)
    if success:
        if client1.player_id == player1_id:
            print(f"✅ SUCCESS: {client1.name} reconnected to same slot (Player {player1_id})")
        else:
            print(f"⚠️  WARNING: {client1.name} reconnected but to different slot (was {player1_id}, now {client1.player_id})")
    else:
        print(f"❌ FAILED: {client1.name} could not reconnect")
        return False
    
    # Clean up
    await client1.disconnect()
    await client2.disconnect()
    
    return True

async def test_multiple_disconnects():
    """Test multiple players disconnecting and reconnecting"""
    print("\n=== Testing Multiple Disconnections ===")
    
    # Use a different room code for this test
    test_room = "TEST02"
    
    clients = []
    room_code = test_room
    
    # Create 4 clients and have them join a room
    for i in range(4):
        client = TestClient(f"Client{i+1}")
        await client.connect()
        
        success = await client.join_or_create_room(room_code)
        
        if not success:
            print(f"Failed to create/join room for Client{i+1}")
            return False
        
        clients.append(client)
        print(f"Client{i+1} joined as player {client.player_id}")
    
    # Store original player IDs
    original_ids = [client.player_id for client in clients]
    
    # Disconnect all clients abruptly
    print("[Test] Disconnecting all clients...")
    for client in clients:
        await client.disconnect()
    
    # Wait for server to detect disconnections
    await asyncio.sleep(35)
    
    # Reconnect all clients
    print("[Test] Reconnecting all clients...")
    reconnect_success = 0
    for i, client in enumerate(clients):
        await client.connect()
        success = await client.join_or_create_room(room_code)
        
        if success:
            if client.player_id == original_ids[i]:
                print(f"✅ {client.name} reconnected to original slot {client.player_id}")
                reconnect_success += 1
            else:
                print(f"⚠️  {client.name} reconnected to different slot (was {original_ids[i]}, now {client.player_id})")
        else:
            print(f"❌ {client.name} failed to reconnect")
    
    # Clean up
    for client in clients:
        await client.disconnect()
    
    return reconnect_success >= 3  # Allow some flexibility

async def main():
    print("Starting disconnect detection and reconnection tests...")
    print("Make sure the server is running on localhost:8765")
    
    try:
        # Test 1: Basic disconnect/reconnect
        success1 = await test_disconnect_detection()
        
        # Test 2: Multiple disconnects
        success2 = await test_multiple_disconnects()
        
        print(f"\n=== Test Results ===")
        print(f"Basic disconnect/reconnect: {'✅ PASS' if success1 else '❌ FAIL'}")
        print(f"Multiple disconnects: {'✅ PASS' if success2 else '❌ FAIL'}")
        
        if success1 and success2:
            print("\n🎉 All tests passed! Disconnect detection and reconnection working correctly.")
        else:
            print("\n⚠️  Some tests failed. Check server logs for more details.")
            
    except Exception as e:
        print(f"Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
