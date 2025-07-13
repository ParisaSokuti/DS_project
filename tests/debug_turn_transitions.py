#!/usr/bin/env python3
"""
Test script to debug turn transitions after hakem plays a card
"""

import asyncio
import websockets
import json
import time

async def test_turn_transitions():
    """Test turn transitions in detail"""
    
    # Clean up any existing processes
    import subprocess
    subprocess.run(['pkill', '-f', 'python.*server.py'], capture_output=True)
    
    # Start server
    server_process = await asyncio.create_subprocess_exec(
        'python', 'backend/server.py',
        cwd='/Users/parisasokuti/my git repo/DS_project',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    await asyncio.sleep(3)
    
    try:
        # Create connections
        players = []
        player_data = []
        
        for i in range(4):
            ws = await websockets.connect("ws://localhost:8765")
            players.append(ws)
            
            # Join room
            await ws.send(json.dumps({
                'type': 'join',
                'username': f'Player{i+1}',
                'room_code': 'DEBUG'
            }))
            
            response = await ws.recv()
            data = json.loads(response)
            player_data.append(data)
            print(f"Player {i+1} joined with ID: {data.get('player_id', 'N/A')}")
        
        # Wait for game to start
        await asyncio.sleep(2)
        
        # Collect all messages to understand the flow
        all_messages = []
        hakem = None
        hakem_ws = None
        hakem_index = None
        
        for i, ws in enumerate(players):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg_data = json.loads(message)
                    all_messages.append((i+1, msg_data))
                    
                    if msg_data.get('type') == 'waiting_for_hokm':
                        hakem = f'Player{i+1}'
                        hakem_ws = ws
                        hakem_index = i
                        print(f"\\n*** {hakem} is the hakem ***")
                        
            except asyncio.TimeoutError:
                pass
        
        if hakem and hakem_ws:
            print(f"\\n=== HOKM SELECTION PHASE ===")
            await hakem_ws.send(json.dumps({
                'type': 'hokm_selected',
                'room_code': 'DEBUG',
                'suit': 'hearts'
            }))
            
            # Wait for hokm selection processing
            await asyncio.sleep(2)
            
            # Read messages after hokm selection
            for i, ws in enumerate(players):
                try:
                    while True:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msg_data = json.loads(message)
                        
                        if msg_data.get('type') == 'turn_start':
                            current_player = msg_data.get('current_player')
                            is_your_turn = msg_data.get('your_turn', False)
                            hand = msg_data.get('hand', [])
                            
                            print(f"\\nPlayer{i+1} received turn_start:")
                            print(f"  Current player: {current_player}")
                            print(f"  Is your turn: {is_your_turn}")
                            print(f"  Hand size: {len(hand)}")
                            
                            if is_your_turn and current_player == hakem:
                                print(f"\\n=== HAKEM PLAYS FIRST CARD ===")
                                if hand:
                                    card_to_play = hand[0]
                                    print(f"Hakem {hakem} playing: {card_to_play}")
                                    
                                    await ws.send(json.dumps({
                                        'type': 'play_card',
                                        'room_code': 'DEBUG',
                                        'player_id': player_data[i]['player_id'],
                                        'card': card_to_play
                                    }))
                                    
                                    # Wait for card play to be processed
                                    await asyncio.sleep(1)
                                    
                                    # Check messages after hakem plays
                                    print(f"\\n=== CHECKING NEXT TURN AFTER HAKEM PLAYS ===")
                                    for j, ws2 in enumerate(players):
                                        try:
                                            while True:
                                                msg = await asyncio.wait_for(ws2.recv(), timeout=1.0)
                                                msg_data2 = json.loads(msg)
                                                
                                                if msg_data2.get('type') == 'turn_start':
                                                    next_current = msg_data2.get('current_player')
                                                    next_your_turn = msg_data2.get('your_turn', False)
                                                    next_hand = msg_data2.get('hand', [])
                                                    
                                                    print(f"  Player{j+1} received turn_start after hakem play:")
                                                    print(f"    Current player: {next_current}")
                                                    print(f"    Is your turn: {next_your_turn}")
                                                    print(f"    Hand size: {len(next_hand)}")
                                                    
                                                    if next_your_turn and next_current != hakem:
                                                        print(f"\\n*** SUCCESS: Next player {next_current} can play! ***")
                                                        if next_hand:
                                                            next_card = next_hand[0]
                                                            print(f"Next player {next_current} playing: {next_card}")
                                                            
                                                            await ws2.send(json.dumps({
                                                                'type': 'play_card',
                                                                'room_code': 'DEBUG',
                                                                'player_id': player_data[j]['player_id'],
                                                                'card': next_card
                                                            }))
                                                            
                                                            print("\\n*** SECOND CARD PLAYED SUCCESSFULLY ***")
                                                            return
                                                        
                                                elif msg_data2.get('type') == 'card_played':
                                                    played_player = msg_data2.get('player')
                                                    played_card = msg_data2.get('card')
                                                    print(f"  Player{j+1} saw card played: {played_player} played {played_card}")
                                                    
                                        except asyncio.TimeoutError:
                                            break
                                    
                                    print(f"\\n*** WAITING FOR NEXT TURN MESSAGES... ***")
                                    await asyncio.sleep(2)
                                    
                                    return
                except asyncio.TimeoutError:
                    break
        
        print("\\n*** TEST COMPLETED ***")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        for ws in players:
            try:
                await ws.close()
            except:
                pass
        
        try:
            server_process.terminate()
            await server_process.wait()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_turn_transitions())
