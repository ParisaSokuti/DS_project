#!/usr/bin/env python3
"""
Simple Game Flow Test

Tests the basic game flow with a unique room to avoid conflicts.
"""

import asyncio
import websockets
import json
import time
import random

async def test_simple_game_flow():
    """Test a simple game flow"""
    room_code = f"TEST_{random.randint(1000, 9999)}"
    print(f"🎮 Testing Game Flow with Room: {room_code}")
    
    clients = []
    
    try:
        # Connect 4 clients
        print("📱 Connecting 4 clients...")
        for i in range(4):
            ws = await websockets.connect("ws://localhost:8765")
            clients.append(ws)
            print(f"  Client {i+1}: Connected")
        
        # All join the same room
        print(f"🚪 Joining room {room_code}...")
        join_responses = []
        
        for i, ws in enumerate(clients):
            join_msg = {'type': 'join', 'room_code': room_code}
            await ws.send(json.dumps(join_msg))
            print(f"  Client {i+1}: Sent join request")
            
            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response_data = json.loads(response)
            join_responses.append(response_data)
            print(f"  Client {i+1}: {response_data.get('type', 'unknown')} - {response_data.get('username', 'no username')}")
        
        # Check if all joined successfully
        successful_joins = sum(1 for r in join_responses if r.get('type') == 'join_success')
        print(f"✅ {successful_joins}/4 clients joined successfully")
        
        if successful_joins == 4:
            print("🎉 All clients joined! Waiting for game to start...")
            
            # Wait for additional messages (team assignment, etc.)
            print("📢 Listening for game messages...")
            
            for i, ws in enumerate(clients):
                try:
                    # Try to receive 3 messages per client
                    for msg_num in range(3):
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(msg)
                        print(f"  Client {i+1} msg {msg_num+1}: {data.get('type', 'unknown')}")
                        
                        # Special handling for hokm selection
                        if data.get('type') == 'initial_deal' and data.get('is_hakem'):
                            print(f"    🎯 Client {i+1} is Hakem! Selecting hokm...")
                            hokm_msg = {'type': 'hokm_selected', 'room_code': room_code, 'suit': 'spades'}
                            await ws.send(json.dumps(hokm_msg))
                            print(f"    ♠️ Hakem selected spades")
                            
                except asyncio.TimeoutError:
                    print(f"  Client {i+1}: No more messages")
                except Exception as e:
                    print(f"  Client {i+1}: Error receiving messages: {e}")
            
            # Try to play a card if we're in gameplay
            print("🃏 Attempting to play cards...")
            for i, ws in enumerate(clients):
                try:
                    # Simple card play attempt
                    if i == 0:  # First client tries to play
                        play_msg = {
                            'type': 'play_card',
                            'room_code': room_code,
                            'player_id': join_responses[i].get('player_id'),
                            'card': 'AS'  # Try to play Ace of Spades
                        }
                        await ws.send(json.dumps(play_msg))
                        print(f"  Client {i+1}: Attempted to play AS")
                        
                        # Try to get response
                        response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        response_data = json.loads(response)
                        print(f"  Client {i+1}: Card play response: {response_data.get('type', 'unknown')}")
                        
                except Exception as e:
                    print(f"  Client {i+1}: Card play failed: {e}")
                    
        else:
            print(f"❌ Only {successful_joins}/4 clients joined. Game cannot start.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        print("🧹 Cleaning up...")
        for i, client in enumerate(clients):
            try:
                await client.close()
                print(f"  Client {i+1}: Disconnected")
            except:
                pass

async def main():
    print("🎮 SIMPLE GAME FLOW TEST")
    print("="*40)
    
    await test_simple_game_flow()
    
    print("="*40)
    print("🎯 TEST COMPLETE")

if __name__ == "__main__":
    asyncio.run(main())
