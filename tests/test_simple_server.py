#!/usr/bin/env python3
import asyncio
import websockets

async def test_server():
    async def handler(websocket, path):
        print(f"Connection from {websocket.remote_address}")
        await websocket.send("Hello from test server!")
        async for message in websocket:
            print(f"Received: {message}")
            await websocket.send(f"Echo: {message}")

    print("Starting test server on port 8765...")
    async with websockets.serve(handler, "0.0.0.0", 8765):
        print("Test server is running and listening on ws://0.0.0.0:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(test_server())
    except KeyboardInterrupt:
        print("\nTest server shutting down...")
