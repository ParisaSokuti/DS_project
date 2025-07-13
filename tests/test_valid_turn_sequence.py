#!/usr/bin/env python3

import asyncio
import websockets
import json
import sys

async def test_valid_turn_sequence():
    """Test that turn sequence works with valid card plays"""
    
    # Connect 4 players
    players = []
    player_ids = []
    for i in range(4):
        ws = await websockets.connect("ws://localhost:8765")
        players.append(ws)
        
        # Join room
        join_message = {
            "type": "join",
            "username": f"Player{i+1}",
            "room_code": "TEST"
        }
        await ws.send(json.dumps(join_message))
        
        # Get join response
        response = await ws.recv()
        join_data = json.loads(response)
        player_ids.append(join_data['player_id'])
        print(f"Player {i+1} joined: {join_data['player_id']}")
    
    print("\n=== Reading all messages ===")
    
    # Read all messages for each player
    all_messages = [[] for _ in range(4)]
    
    for round_num in range(10):  # Multiple rounds to get all messages
        for i, ws in enumerate(players):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                data = json.loads(message)
                all_messages[i].append(data)
                print(f"Player {i+1} got: {data['type']}")
            except asyncio.TimeoutError:
                pass
    
    # Find hakem
    hakem_player = None
    hakem_index = None
    for i, messages in enumerate(all_messages):
        for msg in messages:
            if msg['type'] == 'initial_deal' and msg.get('is_hakem'):
                hakem_player = i
                hakem_index = i
                print(f"\n*** HAKEM FOUND: Player {i+1} ***")
                break
        if hakem_player is not None:
            break
    
    if hakem_player is None:
        print("*** ERROR: No hakem found! ***")
        return
    
    # Hakem selects hokm
    hokm_message = {
        "type": "hokm_selected",
        "room_code": "TEST",
        "suit": "hearts"
    }
    await players[hakem_player].send(json.dumps(hokm_message))
    print(f"\n=== Hakem (Player {hakem_player+1}) selecting hokm ===")
    
    # Read more messages after hokm selection
    for round_num in range(10):  # Multiple rounds to get all messages
        for i, ws in enumerate(players):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                data = json.loads(message)
                all_messages[i].append(data)
                if data['type'] == 'turn_start':
                    print(f"Player {i+1} got turn_start: current_player={data.get('current_player')}, your_turn={data.get('your_turn')}")
            except asyncio.TimeoutError:
                pass
    
    # Find who has the turn (should be hakem)
    current_player = None
    for i, messages in enumerate(all_messages):
        for msg in messages:
            if msg['type'] == 'turn_start' and msg.get('your_turn') == True:
                current_player = i
                print(f"\n*** TURN START: Player {i+1} has the turn ***")
                break
        if current_player is not None:
            break
    
    if current_player is None:
        print("*** ERROR: No player has the turn! ***")
        return
    
    # Get the hakem's hand to play a valid card
    hakem_hand = None
    for msg in all_messages[current_player]:
        if msg['type'] == 'final_deal' and 'hand' in msg:
            hakem_hand = msg['hand']
            break
        elif msg['type'] == 'turn_start' and 'hand' in msg:
            hakem_hand = msg['hand']
            break
    
    if not hakem_hand:
        print("*** ERROR: Could not get hakem's hand! ***")
        return
    
    # Play first card (hakem can play any card)
    first_card = hakem_hand[0]
    player_id = player_ids[current_player]
    
    print(f"\n=== Hakem playing: {first_card} ===")
    play_message = {
        "type": "play_card",
        "room_code": "TEST",
        "player_id": player_id,
        "card": first_card
    }
    await players[current_player].send(json.dumps(play_message))
    
    # Read messages after first card play
    print("\n=== After hakem plays ===")
    next_player_got_turn = False
    for round_num in range(10):
        for i, ws in enumerate(players):
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                data = json.loads(message)
                print(f"Player {i+1} got: {data['type']}")
                if data['type'] == 'turn_start' and data.get('your_turn') == True:
                    next_player_got_turn = True
                    print(f"*** NEXT PLAYER (Player {i+1}) GOT TURN! ***")
                    current_player = i
                elif data['type'] == 'card_played':
                    print(f"  Card played: {data.get('card')} by {data.get('player')}")
            except asyncio.TimeoutError:
                pass
    
    if next_player_got_turn:
        print("\n*** SUCCESS: Turn transition worked! ***")
        
        # Let's try to play one more card
        next_player_hand = None
        for msg in all_messages[current_player]:
            if msg['type'] == 'final_deal' and 'hand' in msg:
                next_player_hand = msg['hand']
                break
            elif msg['type'] == 'turn_start' and 'hand' in msg:
                next_player_hand = msg['hand']
                break
        
        if next_player_hand:
            # Find a card that follows suit (hearts in this case)
            led_suit = first_card.split('_')[1]
            valid_card = None
            for card in next_player_hand:
                if card.split('_')[1] == led_suit:
                    valid_card = card
                    break
            
            if not valid_card:
                # No hearts, can play any card
                valid_card = next_player_hand[0]
            
            player_id = player_ids[current_player]
            
            if player_id:
                print(f"\n=== Next player playing: {valid_card} ===")
                play_message = {
                    "type": "play_card",
                    "room_code": "TEST",
                    "player_id": player_id,
                    "card": valid_card
                }
                await players[current_player].send(json.dumps(play_message))
                
                # Read final messages
                await asyncio.sleep(2)
                for round_num in range(5):
                    for i, ws in enumerate(players):
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            data = json.loads(message)
                            print(f"Player {i+1} got: {data['type']}")
                            if data['type'] == 'card_played':
                                print(f"  Card played: {data.get('card')} by {data.get('player')}")
                        except asyncio.TimeoutError:
                            pass
    else:
        print("\n*** TEST FAILED: Next player didn't get turn! ***")
    
    # Clean up
    for ws in players:
        await ws.close()

if __name__ == "__main__":
    asyncio.run(test_valid_turn_sequence())
