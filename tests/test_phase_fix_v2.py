#!/usr/bin/env python3

import asyncio
import websockets
import json
import time
import traceback

async def test_client(player_number):
    """Test client that joins a room and tracks phase changes"""
    print(f"[Player {player_number}] Starting test client...")
    
    try:
        # Connect to server
        uri = "ws://localhost:8765"
        async with websockets.connect(uri) as websocket:
            print(f"[Player {player_number}] Connected to server")
            
            # Join room
            join_message = {
                'type': 'join',
                'room_code': '9999'
            }
            await websocket.send(json.dumps(join_message))
            print(f"[Player {player_number}] Sent join message")
            
            # Listen for responses with timeout
            timeout_count = 0
            max_timeouts = 20  # Allow up to 20 timeouts (40 seconds)
            
            while timeout_count < max_timeouts:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    print(f"[Player {player_number}] Received {msg_type}: {data}")
                    
                    if msg_type == 'join_success':
                        print(f"[Player {player_number}] ✓ Successfully joined room")
                    elif msg_type == 'phase_change':
                        new_phase = data.get('new_phase')
                        print(f"[Player {player_number}] ✓ Phase changed to: {new_phase}")
                    elif msg_type == 'team_assignment':
                        print(f"[Player {player_number}] ✓ Received team assignment")
                    elif msg_type == 'initial_deal':
                        hand_size = len(data.get('hand', []))
                        is_hakem = data.get('is_hakem', False)
                        hakem = data.get('hakem', 'unknown')
                        print(f"[Player {player_number}] ✓ Received initial hand: {hand_size} cards, Hakem: {hakem}, I am Hakem: {is_hakem}")
                        
                        # If this player is the hakem, select hokm after a short delay
                        if is_hakem:
                            print(f"[Player {player_number}] I am the Hakem! Selecting hokm...")
                            await asyncio.sleep(1.0)  # Small delay
                            hokm_message = {
                                'type': 'hokm_selected',
                                'room_code': '9999',
                                'suit': 'hearts'  # Always select hearts for test
                            }
                            await websocket.send(json.dumps(hokm_message))
                            print(f"[Player {player_number}] Sent hokm selection: hearts")
                    elif msg_type == 'hokm_selected':
                        suit = data.get('suit')
                        hakem = data.get('hakem')
                        print(f"[Player {player_number}] ✓ Hokm selected: {suit} by {hakem}")
                    elif msg_type == 'final_deal':
                        hand_size = len(data.get('hand', []))
                        hokm = data.get('hokm')
                        print(f"[Player {player_number}] ✓ Final deal: {hand_size} cards, Hokm: {hokm}")
                    elif msg_type == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn', False)
                        hand_size = len(data.get('hand', []))
                        print(f"[Player {player_number}] ✓ Turn start: {current_player}'s turn, My turn: {your_turn}, Hand size: {hand_size}")
                    elif msg_type == 'error':
                        print(f"[Player {player_number}] ❌ Error: {data.get('message')}")
                    else:
                        print(f"[Player {player_number}] Received: {msg_type}")
                    
                    # Reset timeout counter on successful message
                    timeout_count = 0
                    
                except asyncio.TimeoutError:
                    timeout_count += 1
                    if timeout_count <= 3:  # Only show first few timeouts
                        print(f"[Player {player_number}] No message (timeout {timeout_count}/{max_timeouts})...")
                    elif timeout_count == max_timeouts:
                        print(f"[Player {player_number}] Maximum timeouts reached, ending test")
                        break
                except websockets.exceptions.ConnectionClosed:
                    print(f"[Player {player_number}] ❌ Connection closed by server")
                    break
                except Exception as e:
                    print(f"[Player {player_number}] ❌ Error receiving message: {e}")
                    break
                    
    except Exception as e:
        print(f"[Player {player_number}] ❌ Connection error: {e}")
        traceback.print_exc()

async def main():
    """Start 4 test clients to fill up a room"""
    print("Starting 4 test clients...")
    
    # Start all clients concurrently with small delays
    tasks = []
    for i in range(4):
        # Add a small delay between client starts
        if i > 0:
            await asyncio.sleep(0.5)
        task = asyncio.create_task(test_client(i + 1))
        tasks.append(task)
    
    # Wait for all clients to complete
    await asyncio.gather(*tasks, return_exceptions=True)
    print("All test clients completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed: {e}")
        traceback.print_exc()
