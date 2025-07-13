#!/usr/bin/env python3
"""
Debug client session handling
"""

import asyncio
import websockets
import json
import os

SERVER_URI = "ws://localhost:8765"
SESSION_FILE = '.player_session'

async def test_session_flow():
    print("=== Testing Session Flow ===")
    
    # Step 1: Connect as new player
    print("\n1. Connecting as new player...")
    async with websockets.connect(SERVER_URI) as ws:
        await ws.send(json.dumps({
            "type": "join",
            "username": "TestPlayer",
            "room_code": "9999"
        }))
        
        response = await ws.recv()
        data = json.loads(response)
        print(f"Response: {data}")
        
        if data.get('type') == 'join_success':
            player_id = data.get('player_id')
            print(f"Got player_id: {player_id}")
            
            # Save to session file
            with open(SESSION_FILE, 'w') as f:
                f.write(player_id)
            print(f"Saved session to {SESSION_FILE}")
    
    print("\n2. Waiting 2 seconds...")
    await asyncio.sleep(2)
    
    # Step 2: Connect using session (reconnect)
    print("\n3. Connecting with session (should reconnect)...")
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            session_player_id = f.read().strip()
        print(f"Found session player_id: {session_player_id}")
        
        async with websockets.connect(SERVER_URI) as ws:
            await ws.send(json.dumps({
                "type": "reconnect",
                "player_id": session_player_id,
                "room_code": "9999"
            }))
            
            response = await ws.recv()
            data = json.loads(response)
            print(f"Reconnect response: {data}")
            
            if data.get('type') == 'reconnect_success':
                print("✅ Reconnection successful!")
            elif data.get('type') == 'error':
                print(f"❌ Reconnection failed: {data.get('message')}")
            else:
                print(f"⚠️  Unexpected response: {data}")
    else:
        print("❌ No session file found!")

if __name__ == "__main__":
    asyncio.run(test_session_flow())
