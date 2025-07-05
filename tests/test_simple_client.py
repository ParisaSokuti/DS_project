#!/usr/bin/env python3
import asyncio
import websockets

async def test_client():
    try:
        async with websockets.connect("ws://localhost:8765") as websocket:
            print("Connected successfully!")
            
            # Receive the welcome message
            response = await websocket.recv()
            print(f"Received: {response}")
            
            # Send a test message
            await websocket.send("Hello server!")
            response = await websocket.recv()
            print(f"Received: {response}")
            
            print("Connection test successful!")
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_client())
