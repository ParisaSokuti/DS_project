#!/usr/bin/env python3
"""
Test script to verify turn sequence works correctly after hakem plays first card.
"""

import asyncio
import websockets
import json
import time

async def test_turn_sequence_fixed():
    """Test turn transitions step by step through the actual game flow"""
    
    # Start the server
    server_process = await asyncio.create_subprocess_exec(
        'python', 'backend/server.py',
        cwd='/Users/parisasokuti/my git repo/DS_project',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    await asyncio.sleep(2)
    
    try:
        # Create 4 player connections
        players = []
        player_ids = []
        player_names = []
        
        for i in range(4):
            ws = await websockets.connect("ws://localhost:8765")
            players.append(ws)
            player_name = f'TestPlayer{i+1}'
            player_names.append(player_name)
            
            # Join room
            await ws.send(json.dumps({
                'type': 'join',
                'username': player_name,
                'room_code': '1234'
            }))
            
            # Read join response
            response = await ws.recv()
            join_data = json.loads(response)
            player_ids.append(join_data.get('player_id'))
            print(f"Player {i+1} ({player_name}) joined with ID: {join_data.get('player_id')}")
        
        # Wait for game to start
        await asyncio.sleep(2)
        
        # Phase 1: Find hakem during initial deal
        hakem_index = None
        hakem_ws = None
        
        print("\\n=== PHASE 1: FINDING HAKEM ===")
        for i, ws in enumerate(players):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    print(f"Player {i+1} received: {data.get('type')}")
                    
                    if data.get('type') == 'initial_deal' and data.get('is_hakem'):
                        hakem_index = i
                        hakem_ws = ws
                        print(f"*** Player {i+1} ({player_names[i]}) is the HAKEM ***")
                        break
                        
            except asyncio.TimeoutError:
                pass
        
        if hakem_index is None:
            print("ERROR: No hakem found!")
            return
        
        # Phase 2: Hakem selects hokm
        print("\\n=== PHASE 2: HAKEM SELECTS HOKM ===")
        await hakem_ws.send(json.dumps({
            'type': 'hokm_selected',
            'room_code': '1234',
            'suit': 'hearts'
        }))
        
        # Wait for hokm selection to be processed
        await asyncio.sleep(2)
        
        # Phase 3: Look for turn_start messages
        print("\\n=== PHASE 3: WAITING FOR TURN START ===")
        hakem_hand = None
        
        for i, ws in enumerate(players):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    print(f"Player {i+1} received: {data.get('type')}")
                    
                    if data.get('type') == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn', False)
                        hand = data.get('hand', [])
                        
                        print(f"  Current player: {current_player}")
                        print(f"  Your turn: {your_turn}")
                        print(f"  Hand size: {len(hand)}")
                        
                        if your_turn and i == hakem_index:
                            hakem_hand = hand
                            print(f"  *** HAKEM {player_names[i]} has the turn! ***")
                            break
                            
            except asyncio.TimeoutError:
                pass
        
        if hakem_hand is None:
            print("ERROR: Hakem didn't get turn_start message!")
            return
        
        # Phase 4: Hakem plays first card
        print("\\n=== PHASE 4: HAKEM PLAYS FIRST CARD ===")
        card_to_play = hakem_hand[0]
        print(f"Hakem {player_names[hakem_index]} playing: {card_to_play}")
        
        await hakem_ws.send(json.dumps({
            'type': 'play_card',
            'room_code': '1234',
            'player_id': player_ids[hakem_index],
            'card': card_to_play
        }))
        
        # Wait for card play to be processed
        await asyncio.sleep(2)
        
        # Phase 5: Check for next player's turn
        print("\\n=== PHASE 5: CHECKING NEXT PLAYER'S TURN ===")
        next_player_found = False
        
        for i, ws in enumerate(players):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    data = json.loads(message)
                    print(f"Player {i+1} received: {data.get('type')}")
                    
                    if data.get('type') == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn', False)
                        hand = data.get('hand', [])
                        
                        print(f"  Current player: {current_player}")
                        print(f"  Your turn: {your_turn}")
                        print(f"  Hand size: {len(hand)}")
                        
                        if your_turn and i != hakem_index:
                            print(f"  *** SUCCESS! Next player {player_names[i]} can play! ***")
                            next_player_found = True
                            
                            # Let the next player play a card
                            if hand:
                                next_card = hand[0]
                                print(f"  Next player playing: {next_card}")
                                await ws.send(json.dumps({
                                    'type': 'play_card',
                                    'room_code': '1234',
                                    'player_id': player_ids[i],
                                    'card': next_card
                                }))
                                print("  *** SECOND CARD PLAYED SUCCESSFULLY! ***")
                            break
                            
            except asyncio.TimeoutError:
                pass
        
        if next_player_found:
            print("\\n*** TEST PASSED: Turn transitions work correctly! ***")
        else:
            print("\\n*** TEST FAILED: Next player didn't get turn! ***")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up
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
    asyncio.run(test_turn_sequence_fixed())
