#!/usr/bin/env python3
"""
Simple test to verify the game starts automatically and see what messages we receive.
"""

import asyncio
import websockets
import json
import time

async def test_client(client_id):
    """Simple client that connects and listens for messages"""
    uri = "ws://localhost:8765"
    print(f"[Client {client_id}] Connecting to {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            # Send join request
            join_message = {
                'type': 'join',
                'username': f'TestPlayer{client_id}',
                'room_code': '1234'
            }
            await websocket.send(json.dumps(join_message))
            print(f"[Client {client_id}] Sent join request")
            
            # Listen for messages for 15 seconds
            start_time = time.time()
            while time.time() - start_time < 15:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    print(f"[Client {client_id}] Received: {data}")
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print(f"[Client {client_id}] Connection closed")
                    break
                    
    except Exception as e:
        print(f"[Client {client_id}] Error: {e}")

async def main():
    """Start 4 clients and see the game progression"""
    print("🚀 Starting 4 test clients to trigger game start...")
    
    # Start 4 clients concurrently
    tasks = []
    for i in range(1, 5):
        task = asyncio.create_task(test_client(i))
        tasks.append(task)
        await asyncio.sleep(0.5)  # Stagger connections slightly
    
    # Wait for all clients to finish
    await asyncio.gather(*tasks)
    print("✅ All clients completed")

if __name__ == "__main__":
    asyncio.run(main())
