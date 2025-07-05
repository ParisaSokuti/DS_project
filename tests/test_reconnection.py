#!/usr/bin/env python3
"""
Manual test for reconnection functionality
"""

import asyncio
import websockets
import json
import time

async def test_reconnection():
    """Test reconnection functionality manually"""
    
    print("=== TESTING RECONNECTION FUNCTIONALITY ===")
    
    # Connect 4 players
    print("\n1. Connecting 4 players...")
    
    connections = []
    for i in range(4):
        try:
            ws = await websockets.connect("ws://localhost:8765")
            await ws.send(json.dumps({
                "type": "join", 
                "room_code": "9999"
            }))
            response = await ws.recv()
            data = json.loads(response)
            print(f"Player {i+1}: {data.get('type', 'unknown')} - {data.get('message', 'No message')}")
            connections.append(ws)
        except Exception as e:
            print(f"Error connecting player {i+1}: {e}")
    
    print(f"Connected {len(connections)} players")
    
    # Disconnect player 3 (index 2)
    print("\n2. Disconnecting Player 3...")
    if len(connections) >= 3:
        await connections[2].close()
        print("Player 3 disconnected")
        
        # Wait a moment for disconnect to be processed
        await asyncio.sleep(1)
        
        # Try to reconnect as new player (should work now)
        print("\n3. Attempting to reconnect...")
        try:
            new_ws = await websockets.connect("ws://localhost:8765")
            await new_ws.send(json.dumps({
                "type": "join",
                "room_code": "9999" 
            }))
            response = await new_ws.recv()
            data = json.loads(response)
            print(f"Reconnection result: {data.get('type', 'unknown')} - {data.get('message', 'No message')}")
            
            if data.get('type') == 'join_success':
                if data.get('reconnected'):
                    print("✅ Successfully reconnected to existing slot!")
                else:
                    print("✅ Successfully joined (new player)")
            else:
                print("❌ Reconnection failed")
                
            await new_ws.close()
            
        except Exception as e:
            print(f"❌ Reconnection error: {e}")
    
    # Clean up remaining connections
    print("\n4. Cleaning up...")
    for ws in connections:
        if not ws.closed:
            await ws.close()
    
    print("=== TEST COMPLETED ===")

if __name__ == '__main__':
    asyncio.run(test_reconnection())
