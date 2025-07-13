#!/usr/bin/env python3
"""
Test reconnection functionality step by step
"""

import asyncio
import websockets
import json

async def test_step_by_step():
    """Test reconnection step by step"""
    
    print("=== STEP-BY-STEP RECONNECTION TEST ===")
    
    # Step 1: Connect just 3 players
    print("\n1. Connecting 3 players to leave room for one more...")
    connections = []
    
    for i in range(3):
        ws = await websockets.connect("ws://localhost:8765")
        await ws.send(json.dumps({"type": "join", "room_code": "9999"}))
        response = await ws.recv()
        data = json.loads(response)
        print(f"  Player {i+1}: {data.get('type', 'unknown')}")
        connections.append(ws)
    
    # Step 2: Connect 4th player
    print("\n2. Connecting 4th player (room should be full now)...")
    ws4 = await websockets.connect("ws://localhost:8765")
    await ws4.send(json.dumps({"type": "join", "room_code": "9999"}))
    response = await ws4.recv()
    data = json.loads(response)
    print(f"  Player 4: {data.get('type', 'unknown')} - {data.get('message', 'No message')}")
    
    # Step 3: Close player 4's connection
    print("\n3. Closing Player 4's connection...")
    await ws4.close()
    await asyncio.sleep(2)  # Give server time to process
    
    # Step 4: Try to reconnect as Player 4
    print("\n4. Attempting to reconnect as Player 4...")
    ws4_new = await websockets.connect("ws://localhost:8765")
    await ws4_new.send(json.dumps({"type": "join", "room_code": "9999"}))
    response = await ws4_new.recv()
    data = json.loads(response)
    
    result_type = data.get('type', 'unknown')
    message = data.get('message', 'No message')
    reconnected = data.get('reconnected', False)
    
    print(f"  Result: {result_type} - {message}")
    print(f"  Reconnected flag: {reconnected}")
    
    if result_type == 'join_success':
        if reconnected:
            print("  ✅ SUCCESS: Properly reconnected to existing slot!")
        else:
            print("  ✅ SUCCESS: Joined (but as new player)")
    elif result_type == 'error' and 'full' in message.lower():
        print("  ❌ FAILED: Still getting 'Room is full' - reconnection not working")
    else:
        print(f"  ❓ UNEXPECTED: {result_type} - {message}")
    
    # Cleanup
    await ws4_new.close()
    for ws in connections:
        await ws.close()
    
    print("\n=== TEST COMPLETE ===")

if __name__ == '__main__':
    asyncio.run(test_step_by_step())
