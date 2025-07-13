#!/usr/bin/env python3
"""
Quick test to verify reconnection functionality
"""

import asyncio
import websockets
import json
import time

class QuickReconnectTest:
    async def run_test(self):
        print("=== Quick Reconnection Test ===")
        
        # Connect and join room
        print("1. Connecting first client...")
        ws1 = await websockets.connect("ws://localhost:8765")
        
        await ws1.send(json.dumps({
            'type': 'join',
            'username': 'TestPlayer1',
            'room_code': 'QUICK1'
        }))
        
        response = await ws1.recv()
        data = json.loads(response)
        print(f"Join response: {data}")
        
        if data.get('type') != 'join_success':
            print("❌ Failed to join room")
            return False
            
        player_id = data.get('player_id')
        print(f"Player ID: {player_id}")
        
        # Add second client
        print("2. Adding second client...")
        ws2 = await websockets.connect("ws://localhost:8765")
        
        await ws2.send(json.dumps({
            'type': 'join',
            'username': 'TestPlayer2',
            'room_code': 'QUICK1'
        }))
        
        response = await ws2.recv()
        data = json.loads(response)
        print(f"Second join response: {data}")
        
        # Disconnect first client abruptly
        print("3. Disconnecting first client...")
        await ws1.close()
        
        # Wait for disconnect detection
        print("4. Waiting for disconnect detection (10 seconds)...")
        await asyncio.sleep(10)
        
        # Reconnect first client
        print("5. Reconnecting first client...")
        ws1_new = await websockets.connect("ws://localhost:8765")
        
        await ws1_new.send(json.dumps({
            'type': 'join',
            'username': 'TestPlayer1',
            'room_code': 'QUICK1'
        }))
        
        response = await ws1_new.recv()
        data = json.loads(response)
        print(f"Reconnect response: {data}")
        
        # Check if we got the same player ID
        new_player_id = data.get('player_id')
        if new_player_id == player_id:
            print(f"✅ SUCCESS: Reconnected to same slot {player_id}")
            success = True
        else:
            print(f"❌ FAILED: Got different player ID (was {player_id}, now {new_player_id})")
            success = False
        
        # Clean up
        await ws1_new.close()
        await ws2.close()
        
        return success

async def main():
    test = QuickReconnectTest()
    result = await test.run_test()
    
    print(f"\nTest result: {'✅ PASS' if result else '❌ FAIL'}")

if __name__ == "__main__":
    asyncio.run(main())
