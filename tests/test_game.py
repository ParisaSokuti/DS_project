#!/usr/bin/env python3

import asyncio
import websockets
import json
import sys
import os
import traceback

async def run_client(client_id, room_code="9999"):
    uri = "ws://localhost:8765"
    
    try:
        async with websockets.connect(uri) as ws:
            print(f"Client {client_id}: Connected to server")
            
            # Join room
            await ws.send(json.dumps({
                "type": "join",
                "room_code": room_code
            }))
            print(f"Client {client_id}: Join request sent")
            
            # Process messages for 180 seconds
            start_time = asyncio.get_event_loop().time()
            is_hakem = False
            
            while asyncio.get_event_loop().time() - start_time < 180:  # 3 minutes timeout
                try:
                    # Add a timeout to ensure we can exit cleanly
                    response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(response)
                    print(f"Client {client_id} received: {data}")
                    
                    # Check if we are the hakem
                    if data.get('type') == 'initial_deal' and data.get('is_hakem', False):
                        is_hakem = True
                        print(f"CLIENT {client_id} IS THE HAKEM!")
                    
                    # Handle hokm selection if we're the hakem and phase changes to waiting_for_hokm
                    if is_hakem and data.get('type') == 'phase_change' and data.get('new_phase') == 'waiting_for_hokm':
                        print(f"CLIENT {client_id}: SELECTING HOKM AS HEARTS")
                        await ws.send(json.dumps({
                            'type': 'hokm_selected',
                            'suit': 'hearts',
                            'room_code': room_code
                        }))
                        print(f"CLIENT {client_id}: SENT HOKM SELECTION")
                    
                    # Print detailed message for other important events
                    if data.get('type') == 'team_assignment':
                        print(f"CLIENT {client_id}: TEAM ASSIGNMENT RECEIVED")
                        print(f"Teams: {data.get('teams')}")
                        print(f"Hakem: {data.get('hakem')}")
                    
                    if data.get('type') == 'hokm_selected':
                        print(f"CLIENT {client_id}: HOKM SELECTED NOTIFICATION RECEIVED")
                        print(f"Hokm: {data.get('suit')}, Hakem: {data.get('hakem')}")
                    
                    if data.get('type') == 'final_deal':
                        print(f"CLIENT {client_id}: FINAL DEAL RECEIVED")
                        print(f"Hand size: {len(data.get('hand', []))}")
                    
                except asyncio.TimeoutError:
                    # This is expected, just continue the loop
                    continue
                except Exception as e:
                    print(f"Client {client_id} message processing error: {e}")
                    traceback.print_exc()
    except Exception as e:
        print(f"Client {client_id} connection error: {e}")
        traceback.print_exc()

async def main():
    # Run 4 clients to simulate a game
    tasks = [run_client(i) for i in range(1, 5)]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript stopped by user")
    except Exception as e:
        print(f"Error: {e}")
