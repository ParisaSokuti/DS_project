#!/usr/bin/env python
# clear_room.py - A simple utility to clear a room in the Hokm game

import asyncio
import websockets
import json
import sys

SERVER_URI = "ws://localhost:8765"

async def clear_room(room_code="9999"):
    """Connect to the server and send a clear_room command"""
    try:
        print(f"Connecting to server to clear room {room_code}...")
        async with websockets.connect(SERVER_URI) as ws:
            await ws.send(json.dumps({
                'type': 'clear_room',
                'room_code': room_code
            }))
            
            # Wait for response
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                if data.get('type') == 'info':
                    print(f"✅ {data.get('message', 'Room cleared successfully')}")
                    return True
                elif data.get('type') == 'error':
                    print(f"❌ Error: {data.get('message', 'Unknown error')}")
                    return False
                else:
                    print(f"Got response: {data}")
                    return True
            except asyncio.TimeoutError:
                print("No response from server, but command was sent.")
                return True
            
    except Exception as e:
        print(f"❌ Failed to clear room: {e}")
        return False

if __name__ == "__main__":
    room_code = "9999"  # Default room code
    if len(sys.argv) > 1:
        room_code = sys.argv[1]
        
    print(f"Clearing room {room_code}...")
    asyncio.run(clear_room(room_code))
