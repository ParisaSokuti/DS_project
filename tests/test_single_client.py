#!/usr/bin/env python3
"""
Test with single client to see server debug output
"""
import asyncio
import websockets
import json

async def test_single_client():
    print("Testing single client...")
    
    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            print("Connected")
            
            # Send join
            await ws.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            print("Sent join")
            
            # Listen for 5 seconds
            timeout = 0
            while timeout < 10:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    data = json.loads(message)
                    print(f"[{timeout:02d}] Received: {data.get('type')}")
                except asyncio.TimeoutError:
                    timeout += 1
                    continue
                except Exception as e:
                    print(f"Error: {e}")
                    break
                    
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_single_client())
