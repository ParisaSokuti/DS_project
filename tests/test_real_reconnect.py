#!/usr/bin/env python3
"""
Simulate actual client disconnect and reconnect scenario
"""

import asyncio
import websockets
import json
import time

async def simulate_disconnect_reconnect():
    """Simulate the actual scenario where a client disconnects and tries to reconnect"""
    
    print("=== SIMULATING REAL DISCONNECT/RECONNECT SCENARIO ===")
    
    # Step 1: Connect 3 players first
    print("\n1. Connecting first 3 players...")
    connections = []
    
    for i in range(3):
        try:
            ws = await websockets.connect("ws://localhost:8765")
            await ws.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            response = await ws.recv()
            data = json.loads(response)
            print(f"Player {i+1}: {data.get('message', data.get('type', 'success'))}")
            connections.append(ws)
        except Exception as e:
            print(f"Error connecting player {i+1}: {e}")
    
    # Step 2: Connect 4th player  
    print("\n2. Connecting 4th player...")
    try:
        ws4 = await websockets.connect("ws://localhost:8765")
        await ws4.send(json.dumps({
            "type": "join",
            "room_code": "9999"
        }))
        response = await ws4.recv()
        data = json.loads(response)
        print(f"Player 4: {data.get('message', data.get('type', 'success'))}")
        
        # Step 3: Disconnect player 4 immediately (simulate network issue)
        print("\n3. Player 4 disconnects (simulating network issue)...")
        await ws4.close()
        print("Player 4 connection closed")
        
        # Wait for server to process disconnect
        await asyncio.sleep(2)
        
        # Step 4: Player 4 tries to reconnect
        print("\n4. Player 4 tries to reconnect...")
        try:
            ws4_reconnect = await websockets.connect("ws://localhost:8765")
            await ws4_reconnect.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            response = await ws4_reconnect.recv()
            data = json.loads(response)
            
            print(f"Reconnection attempt: {data.get('type')} - {data.get('message', 'No message')}")
            
            if data.get('type') == 'join_success':
                if data.get('reconnected'):
                    print("✅ SUCCESS: Reconnected to original slot!")
                else:
                    print("✅ SUCCESS: Joined as new player")
            elif data.get('type') == 'error' and 'full' in data.get('message', '').lower():
                print("❌ FAILED: Still getting 'Room is full' error")
            else:
                print(f"❌ FAILED: Unexpected response")
                
            await ws4_reconnect.close()
            
        except Exception as e:
            print(f"❌ Reconnection error: {e}")
            
    except Exception as e:
        print(f"Error with player 4: {e}")
    
    # Cleanup
    print("\n5. Cleaning up remaining connections...")
    for ws in connections:
        try:
            if not ws.closed:
                await ws.close()
        except:
            pass
    
    print("=== TEST COMPLETED ===")

if __name__ == '__main__':
    asyncio.run(simulate_disconnect_reconnect())
