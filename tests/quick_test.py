#!/usr/bin/env python3
"""Quick test to see if server is responsive"""

import asyncio
import websockets
import json

async def simple_test():
    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            await ws.send(json.dumps({"type": "join", "room_code": "test123"}))
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"Server responded: {response}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(simple_test())
