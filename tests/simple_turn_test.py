#!/usr/bin/env python3
"""
Simple test to check turn transitions after hakem plays
"""

import asyncio
import websockets
import json

async def simple_turn_test():
    """Simple test that doesn't start its own server"""
    
    try:
        # Create 4 players
        players = []
        player_ids = []
        
        for i in range(4):
            ws = await websockets.connect("ws://localhost:8765")
            players.append(ws)
            
            # Join room
            await ws.send(json.dumps({
                'type': 'join',
                'username': f'Player{i+1}',
                'room_code': 'TEST'
            }))
            
            # Get join response
            response = await ws.recv()
            data = json.loads(response)
            player_ids.append(data.get('player_id'))
            print(f"Player {i+1} joined: {data.get('player_id')}")
        
        # Wait for game to start
        await asyncio.sleep(5)  # Increased timeout
        
        # Read all available messages and look for hakem
        hakem_index = None
        hakem_hand = None
        
        print("\\n=== Reading all messages ===")
        for i, ws in enumerate(players):
            print(f"\\nPlayer {i+1} messages:")
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=3.0)  # Increased timeout
                    data = json.loads(message)
                    msg_type = data.get('type')
                    print(f"  {msg_type}")
                    
                    if msg_type == 'initial_deal':
                        is_hakem = data.get('is_hakem', False)
                        hand = data.get('hand', [])
                        print(f"    is_hakem: {is_hakem}")
                        print(f"    hand_size: {len(hand)}")
                        
                        if is_hakem:
                            hakem_index = i
                            hakem_hand = hand
                            print(f"    *** HAKEM FOUND! ***")
                    
                    elif msg_type == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn')
                        hand = data.get('hand', [])
                        print(f"    current_player: {current_player}")
                        print(f"    your_turn: {your_turn}")
                        print(f"    hand_size: {len(hand)}")
                        
                        if your_turn:
                            # Store this for potential card play
                            if i == hakem_index:
                                hakem_hand = hand
                                print(f"    *** HAKEM HAS TURN! ***")
                    
            except asyncio.TimeoutError:
                pass
        
        if hakem_index is None:
            print("\\nERROR: Hakem not found!")
            return
            
        # Wait for hokm selection phase
        print(f"\\n=== Hakem (Player {hakem_index+1}) selecting hokm ===")
        await players[hakem_index].send(json.dumps({
            'type': 'hokm_selected',
            'room_code': 'TEST',
            'suit': 'hearts'
        }))
        
        # Wait for hokm processing
        await asyncio.sleep(5)  # Increased timeout
        
        # Read messages after hokm selection
        print("\\n=== After hokm selection ===")
        for i, ws in enumerate(players):
            print(f"\\nPlayer {i+1} messages:")
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=3.0)  # Increased timeout
                    data = json.loads(message)
                    msg_type = data.get('type')
                    print(f"  {msg_type}")
                    
                    if msg_type == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn')
                        hand = data.get('hand', [])
                        print(f"    current_player: {current_player}")
                        print(f"    your_turn: {your_turn}")
                        print(f"    hand_size: {len(hand)}")
                        
                        if your_turn and i == hakem_index:
                            print(f"    *** HAKEM HAS TURN AFTER HOKM! ***")
                            hakem_hand = hand
                            
            except asyncio.TimeoutError:
                pass
        
        if not hakem_hand:
            print("\\nERROR: Hakem doesn't have cards to play!")
            return
            
        # Hakem plays first card
        card_to_play = hakem_hand[0]
        print(f"\\n=== Hakem playing: {card_to_play} ===")
        await players[hakem_index].send(json.dumps({
            'type': 'play_card',
            'room_code': 'TEST',
            'player_id': player_ids[hakem_index],
            'card': card_to_play
        }))
        
        # Wait for card play processing
        await asyncio.sleep(2)
        
        # Check for next player's turn
        print("\\n=== After hakem plays ===")
        next_turn_found = False
        
        for i, ws in enumerate(players):
            print(f"\\nPlayer {i+1} messages:")
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=3.0)  # Increased timeout
                    data = json.loads(message)
                    msg_type = data.get('type')
                    print(f"  {msg_type}")
                    
                    if msg_type == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn')
                        hand = data.get('hand', [])
                        print(f"    current_player: {current_player}")
                        print(f"    your_turn: {your_turn}")
                        print(f"    hand_size: {len(hand)}")
                        
                        if your_turn and i != hakem_index:
                            print(f"    *** SUCCESS! Next player {i+1} has turn! ***")
                            next_turn_found = True
                            
                            # Play next card
                            if hand:
                                next_card = hand[0]
                                print(f"    Playing: {next_card}")
                                await ws.send(json.dumps({
                                    'type': 'play_card',
                                    'room_code': 'TEST',
                                    'player_id': player_ids[i],
                                    'card': next_card
                                }))
                                print(f"    *** NEXT CARD PLAYED! ***")
                                
            except asyncio.TimeoutError:
                pass
        
        if next_turn_found:
            print("\\n*** TEST PASSED: Turn transitions work! ***")
        else:
            print("\\n*** TEST FAILED: Next player didn't get turn! ***")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        for ws in players:
            try:
                await ws.close()
            except:
                pass

if __name__ == "__main__":
    asyncio.run(simple_turn_test())
