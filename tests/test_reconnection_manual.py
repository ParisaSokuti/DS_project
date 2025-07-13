#!/usr/bin/env python3
"""
Test script to manually verify the reconnection logic step by step
"""

import asyncio
import websockets
import json
import uuid
import os
import time

SERVER_URI = "ws://localhost:8765"

async def test_client_connection(client_name, player_id=None):
    """Test a single client connection"""
    print(f"\n🔍 {client_name}: Connecting to server...")
    
    try:
        async with websockets.connect(SERVER_URI) as ws:
            if player_id:
                # Send reconnect message
                message = {
                    "type": "reconnect",
                    "player_id": player_id,
                    "room_code": "9999"
                }
                print(f"📤 {client_name}: Sending reconnect message with player_id: {player_id[:8]}...")
            else:
                # Send join message
                message = {
                    "type": "join",
                    "username": client_name,
                    "room_code": "9999"
                }
                print(f"📤 {client_name}: Sending join message...")
            
            await ws.send(json.dumps(message))
            
            # Wait for response
            try:
                response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                response = json.loads(response_raw)
                print(f"📥 {client_name}: Received response:")
                print(f"   Type: {response.get('type')}")
                
                if response.get('type') == 'join_success':
                    returned_player_id = response.get('player_id')
                    username = response.get('username')
                    player_number = response.get('player_number')
                    reconnected = response.get('reconnected', False)
                    
                    print(f"   Username: {username}")
                    print(f"   Player ID: {returned_player_id[:8]}...")
                    print(f"   Player Number: {player_number}")
                    print(f"   Reconnected: {reconnected}")
                    
                    return returned_player_id
                elif response.get('type') == 'reconnect_success':
                    returned_player_id = response.get('player_id')
                    username = response.get('username')
                    
                    print(f"   Username: {username}")
                    print(f"   Player ID: {returned_player_id[:8]}...")
                    print(f"   Reconnection successful!")
                    
                    return returned_player_id
                elif response.get('type') == 'error':
                    print(f"   Error: {response.get('message')}")
                    return None
                else:
                    print(f"   Unexpected response: {response}")
                    return None
                    
            except asyncio.TimeoutError:
                print(f"❌ {client_name}: Timeout waiting for server response")
                return None
                
    except Exception as e:
        print(f"❌ {client_name}: Connection failed: {e}")
        return None

async def main():
    """Main test sequence"""
    print("🧪 Testing reconnection logic step by step")
    
    # Step 1: First client connects
    print("\n=== STEP 1: First client connects ===")
    player_id_1 = await test_client_connection("Client1")
    
    if not player_id_1:
        print("❌ First client connection failed, aborting test")
        return
    
    print(f"✅ Client1 connected with player_id: {player_id_1[:8]}...")
    
    # Step 2: Wait a moment, then "disconnect" (connection closes automatically)
    print("\n=== STEP 2: Client1 disconnects (connection closed) ===")
    await asyncio.sleep(2)
    print("⏳ Client1 connection closed, waiting for server to detect disconnect...")
    await asyncio.sleep(3)  # Give server time to detect disconnect
    
    # Step 3: Second client tries to connect (should get new slot)
    print("\n=== STEP 3: New client connects (should get new slot) ===")
    player_id_2 = await test_client_connection("Client2")
    
    if not player_id_2:
        print("❌ Second client connection failed")
        return
    
    print(f"✅ Client2 connected with player_id: {player_id_2[:8]}...")
    
    # Step 4: Original client tries to reconnect (should get original slot back)
    print("\n=== STEP 4: Original client reconnects (should get original slot) ===")
    reconnected_id = await test_client_connection("Client1_Reconnect", player_id_1)
    
    if not reconnected_id:
        print("❌ Reconnection failed")
        return
    
    print(f"✅ Client1 reconnected with player_id: {reconnected_id[:8]}...")
    
    # Compare IDs
    print(f"\n📊 Results:")
    print(f"   Original Client1 ID: {player_id_1[:8]}...")
    print(f"   New Client2 ID: {player_id_2[:8]}...")
    print(f"   Reconnected Client1 ID: {reconnected_id[:8]}...")
    
    if player_id_1 == reconnected_id:
        print("✅ SUCCESS: Original client reconnected to same slot")
    else:
        print("❌ FAILURE: Reconnection gave different player ID")
        
    if player_id_1 != player_id_2:
        print("✅ SUCCESS: New client got different slot")
    else:
        print("❌ FAILURE: New client got same slot as disconnected player")

if __name__ == "__main__":
    asyncio.run(main())
