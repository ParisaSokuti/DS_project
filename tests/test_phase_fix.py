#!/usr/bin/env python3
"""
Quick test to verify the phase transition fix
"""
import asyncio
import websockets
import json
import sys

async def test_client(client_id):
    """Test a single client connection"""
    print(f"[CLIENT {client_id}] Connecting...")
    try:
        async with websockets.connect("ws://localhost:8765") as ws:
            # Send join message
            await ws.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            print(f"[CLIENT {client_id}] Sent join message")
            
            # Listen for messages for 15 seconds
            timeout_count = 0
            while timeout_count < 15:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(message)
                    msg_type = data.get('type')
                    print(f"[CLIENT {client_id}] Received: {msg_type}")
                    
                    if msg_type == 'join_success':
                        print(f"[CLIENT {client_id}] Successfully joined as {data.get('username')}")
                    elif msg_type == 'phase_change':
                        print(f"[CLIENT {client_id}] Phase changed to: {data.get('new_phase')}")
                    elif msg_type == 'team_assignment':
                        print(f"[CLIENT {client_id}] Team assignment received")
                        hakem = data.get('hakem')
                        print(f"[CLIENT {client_id}] Hakem is: {hakem}")
                    elif msg_type == 'initial_deal':
                        print(f"[CLIENT {client_id}] Initial deal received")
                        hand = data.get('hand', [])
                        is_hakem = data.get('is_hakem', False)
                        print(f"[CLIENT {client_id}] Hand size: {len(hand)}, Is Hakem: {is_hakem}")
                        
                        # If we're the hakem, select hokm
                        if is_hakem:
                            print(f"[CLIENT {client_id}] Selecting hearts as hokm")
                            await ws.send(json.dumps({
                                "type": "hokm_selected",
                                "suit": "hearts",
                                "room_code": "9999"
                            }))
                    elif msg_type == 'hokm_selected':
                        suit = data.get('suit')
                        print(f"[CLIENT {client_id}] Hokm selected: {suit}")
                    elif msg_type == 'final_deal':
                        print(f"[CLIENT {client_id}] Final deal received")
                        hand = data.get('hand', [])
                        print(f"[CLIENT {client_id}] Final hand size: {len(hand)}")
                    elif msg_type == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn', False)
                        print(f"[CLIENT {client_id}] Turn start - Current: {current_player}, Your turn: {your_turn}")
                        
                        if your_turn:
                            print(f"[CLIENT {client_id}] It's my turn! Gameplay phase reached!")
                            return True  # Success - we reached gameplay
                    
                except asyncio.TimeoutError:
                    timeout_count += 1
                    continue
                except Exception as e:
                    print(f"[CLIENT {client_id}] Error: {e}")
                    break
            
            print(f"[CLIENT {client_id}] Test completed (timeout after 15 seconds)")
            return False
            
    except Exception as e:
        print(f"[CLIENT {client_id}] Connection error: {e}")
        return False

async def main():
    """Run 4 clients simultaneously"""
    print("🎮 Testing phase transitions with 4 clients...")
    
    # Start 4 clients
    tasks = []
    for i in range(4):
        task = asyncio.create_task(test_client(i+1))
        tasks.append(task)
    
    # Wait for all to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if r is True)
    print(f"\n✅ Test Results: {success_count}/4 clients reached gameplay phase")
    
    if success_count >= 1:
        print("🎉 SUCCESS: Phase transitions are working!")
    else:
        print("❌ FAILURE: No clients reached gameplay phase")

if __name__ == "__main__":
    asyncio.run(main())
