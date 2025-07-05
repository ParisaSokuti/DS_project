#!/usr/bin/env python3
"""
Simple test to debug join process
"""
import asyncio
import websockets
import json
import sys

async def test_single_join():
    """Test a single client join"""
    print("Testing single client join...")
    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            print("Connected to server")
            
            # Send join message
            join_msg = {
                "type": "join",
                "room_code": "9999"
            }
            await ws.send(json.dumps(join_msg))
            print("Sent join message")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)
                print(f"Received: {data}")
                
                if data.get('type') == 'join_success':
                    print("✅ Join successful!")
                    return True
                else:
                    print(f"❌ Unexpected response: {data}")
                    return False
                    
            except asyncio.TimeoutError:
                print("❌ No response received within 5 seconds")
                return False
                
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_single_join())
    print(f"Test result: {result}")
