#!/usr/bin/env python3
"""
Test with longer monitoring to see if game starts after all joins
"""
import asyncio
import websockets
import json

async def test_with_longer_wait():
    """Test with longer wait to see if game starts"""
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
    
    # Listen for responses for 20 seconds (longer wait)
    print("Listening for responses for 20 seconds...")
    timeout_count = 0
    while timeout_count < 40:  # 20 seconds total
        for i, ws in enumerate(clients):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                data = json.loads(message)
                msg_type = data.get('type')
                print(f"[{timeout_count:02d}] Client {i+1} received: {msg_type}")
                
                # Show details for important messages
                if msg_type in ['phase_change', 'team_assignment', 'initial_deal']:
                    print(f"    Details: {data}")
                
                # If we're the hakem and get initial_deal, select hokm
                if data.get('type') == 'initial_deal' and data.get('is_hakem'):
                    print(f"    Client {i+1} is hakem, selecting hearts")
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
        
        timeout_count += 1
    
    # Close all clients
    for i, ws in enumerate(clients):
        try:
            await ws.close()
        except:
            pass
    
    print("Test completed after 20 seconds")

if __name__ == "__main__":
    asyncio.run(test_with_longer_wait())
