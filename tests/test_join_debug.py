#!/usr/bin/env python3
"""
Test with debug output to see what happens after 4 players join
"""
import asyncio
import websockets
import json

async def test_join_debug():
    """Test join process with debug output"""
    clients = []
    
    print("Connecting 4 clients...")
    
    # Connect all clients first
    for i in range(4):
        ws = await websockets.connect("ws://localhost:8765")
        clients.append(ws)
        print(f"Client {i+1} connected")
    
    # Send join messages
    for i, ws in enumerate(clients):
        await ws.send(json.dumps({
            "type": "join",
            "room_code": "9999"
        }))
        print(f"Client {i+1} sent join message")
    
    # Listen for responses for 10 seconds
    print("Listening for responses...")
    timeout_count = 0
    while timeout_count < 10:
        for i, ws in enumerate(clients):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                data = json.loads(message)
                print(f"Client {i+1} received: {data.get('type')} - {data}")
                
                # If we're the hakem and get initial_deal, select hokm
                if data.get('type') == 'initial_deal' and data.get('is_hakem'):
                    print(f"Client {i+1} is hakem, selecting hearts")
                    await ws.send(json.dumps({
                        "type": "hokm_selected",
                        "suit": "hearts",
                        "room_code": "9999"
                    }))
                    
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                print(f"Client {i+1} disconnected")
                break
            except Exception as e:
                print(f"Client {i+1} error: {e}")
        
        timeout_count += 0.5
    
    # Close all clients
    for i, ws in enumerate(clients):
        try:
            await ws.close()
        except:
            pass
    
    print("Test completed")

if __name__ == "__main__":
    asyncio.run(test_join_debug())
