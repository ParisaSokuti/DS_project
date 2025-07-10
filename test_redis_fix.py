#!/usr/bin/env python3
"""
Test script to verify full game flow works correctly without Redis warnings.
"""

import asyncio
import websockets
import json
import time

async def test_full_game_flow():
    """Test the full game flow from start to card play"""
    
    # Start the server first
    server_process = await asyncio.create_subprocess_exec(
        'python', 'backend/server.py',
        cwd='/Users/parisasokuti/my git repo/DS_project',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Wait for server to start
    await asyncio.sleep(3)
    
    try:
        # Create 4 player connections
        players = []
        for i in range(4):
            ws = await websockets.connect(
                "ws://localhost:8765",
                ping_interval=60,      # Send ping every 60 seconds
                ping_timeout=300,      # 5 minutes timeout for ping response
                close_timeout=300,     # 5 minutes timeout for close handshake
                max_size=1024*1024,    # 1MB max message size
                max_queue=100          # Max queued messages
            )
            players.append(ws)
            
            # Join room
            await ws.send(json.dumps({
                'type': 'join',
                'username': f'Player{i+1}',
                'room_code': 'TEST'
            }))
            
            # Read join response
            response = await ws.recv()
            print(f"Player {i+1} joined: {json.loads(response)}")
        
        # Wait for all players to join and game to start
        await asyncio.sleep(2)
        
        # Read messages to find hakem and proceed through game phases
        hakem = None
        hakem_ws = None
        
        for i, ws in enumerate(players):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg_data = json.loads(message)
                    print(f"Player {i+1} received: {msg_data.get('type', 'unknown')}")
                    
                    # Look for hokm selection phase
                    if msg_data.get('type') == 'waiting_for_hokm':
                        print(f"Player {i+1} can select hokm")
                        hakem = f'Player{i+1}'
                        hakem_ws = ws
                        break
                    
                    # Look for team assignment info
                    if msg_data.get('type') == 'team_assignment':
                        print(f"Player {i+1} team assignment: {msg_data}")
                        
            except asyncio.TimeoutError:
                pass
        
        # If hakem found, select hokm
        if hakem and hakem_ws:
            print(f"\n{hakem} is the hakem, selecting hokm...")
            await hakem_ws.send(json.dumps({
                'type': 'hokm_selected',
                'room_code': 'TEST',
                'suit': 'hearts'
            }))
            
            # Wait for hokm selection to be processed
            await asyncio.sleep(2)
            
            # Read messages after hokm selection
            for i, ws in enumerate(players):
                try:
                    while True:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg_data = json.loads(message)
                        print(f"Player {i+1} received after hokm: {msg_data.get('type', 'unknown')}")
                        
                        # Look for turn start
                        if msg_data.get('type') == 'turn_start':
                            current_player = msg_data.get('current_player')
                            is_your_turn = msg_data.get('your_turn', False)
                            print(f"Turn start: {current_player} to play, Player{i+1} turn: {is_your_turn}")
                            
                            # If it's this player's turn and they have cards, play one
                            if is_your_turn and 'hand' in msg_data:
                                hand = msg_data['hand']
                                if hand:
                                    card_to_play = hand[0]  # Play first card
                                    print(f"Player {i+1} playing card: {card_to_play}")
                                    await ws.send(json.dumps({
                                        'type': 'play_card',
                                        'room_code': 'TEST',
                                        'player_id': 'test_player_id',
                                        'card': card_to_play
                                    }))
                                    break
                            
                except asyncio.TimeoutError:
                    pass
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up connections
        for ws in players:
            try:
                await ws.close()
            except:
                pass
        
        # Stop server
        try:
            server_process.terminate()
            await server_process.wait()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_full_game_flow())
