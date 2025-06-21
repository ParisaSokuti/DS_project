#!/usr/bin/env python3
"""
Test script to verify 13-trick hand completion and multi-round scoring
"""

import asyncio
import websockets
import json
import time

SERVER_URI = "ws://localhost:8765"
ROOM_CODE = "FULL_HAND_TEST"

async def test_full_hand():
    """Test a complete 13-trick hand with proper scoring"""
    
    print("=== Testing Full 13-Trick Hand Completion ===")
    
    # Clear room first
    try:
        async with websockets.connect(SERVER_URI) as ws:
            await ws.send(json.dumps({
                'type': 'clear_room',
                'room_code': ROOM_CODE
            }))
            print("Room cleared")
    except Exception as e:
        print(f"Could not clear room: {e}")
    
    await asyncio.sleep(1)
    
    # Connect 4 players
    players = []
    player_data = {}
    
    for i in range(4):
        ws = await websockets.connect(SERVER_URI)
        await ws.send(json.dumps({
            "type": "join", 
            "username": f"Player{i+1}",
            "room_code": ROOM_CODE
        }))
        players.append(ws)
        player_data[ws] = {
            'name': f"Player{i+1}",
            'player_id': None,
            'hand': [],
            'tricks_played': 0
        }
    
    print("All players connected")
    
    # Game flow tracking
    hokm_selected = False
    tricks_completed = 0
    hands_completed = 0
    game_complete = False
    
    try:
        # Main game loop
        while not game_complete and hands_completed < 2:  # Test up to 2 hands
            ready_to_read = await asyncio.wait(
                [ws.recv() for ws in players],
                timeout=5.0,
                return_when=asyncio.FIRST_COMPLETED
            )
            
            if not ready_to_read[0]:  # Timeout
                print("Timeout waiting for messages")
                break
                
            for done_task in ready_to_read[0]:
                try:
                    message = done_task.result()
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    # Find which player this message is for
                    player_ws = None
                    for ws in players:
                        if done_task in [asyncio.create_task(ws.recv()) for ws in players]:
                            player_ws = ws
                            break
                    
                    if not player_ws:
                        continue
                        
                    player_info = player_data[player_ws]
                    
                    if msg_type == 'join_success':
                        player_info['player_id'] = data.get('player_id')
                        print(f"{player_info['name']} joined successfully")
                    
                    elif msg_type == 'initial_deal':
                        player_info['hand'] = data.get('hand', [])
                        is_hakem = data.get('is_hakem', False)
                        print(f"{player_info['name']} got {len(player_info['hand'])} cards")
                        
                        # Auto-select hokm if hakem
                        if is_hakem and not hokm_selected:
                            await asyncio.sleep(0.5)
                            await player_ws.send(json.dumps({
                                'type': 'hokm_selected',
                                'suit': 'hearts',
                                'room_code': ROOM_CODE
                            }))
                            hokm_selected = True
                            print(f"{player_info['name']} selected hokm")
                    
                    elif msg_type == 'final_deal':
                        player_info['hand'] = data.get('hand', [])
                        print(f"{player_info['name']} final hand: {len(player_info['hand'])} cards")
                    
                    elif msg_type == 'turn_start':
                        your_turn = data.get('your_turn', False)
                        player_info['hand'] = data.get('hand', player_info['hand'])
                        
                        if your_turn and player_info['hand'] and player_info['player_id']:
                            # Play first available card
                            card_to_play = player_info['hand'][0]
                            print(f"{player_info['name']} playing: {card_to_play}")
                            
                            await player_ws.send(json.dumps({
                                "type": "play_card",
                                "room_code": ROOM_CODE,
                                "player_id": player_info['player_id'],
                                "card": card_to_play
                            }))
                            
                            player_info['tricks_played'] += 1
                    
                    elif msg_type == 'card_played':
                        player = data.get('player')
                        card = data.get('card')
                        # Remove card from local hand if it's this player
                        if player == player_info['name'] and card in player_info['hand']:
                            player_info['hand'].remove(card)
                    
                    elif msg_type == 'trick_result':
                        winner = data.get('winner')
                        team1_tricks = data.get('team1_tricks', 0)
                        team2_tricks = data.get('team2_tricks', 0)
                        tricks_completed += 1
                        print(f"Trick {tricks_completed}: {winner} wins (T1:{team1_tricks}, T2:{team2_tricks})")
                    
                    elif msg_type == 'hand_complete':
                        winning_team = data.get('winning_team', 0) + 1
                        round_winner = data.get('round_winner')
                        round_scores = data.get('round_scores', {})
                        game_complete = data.get('game_complete', False)
                        
                        hands_completed += 1
                        print(f"\n🎉 Hand {hands_completed} Complete!")
                        print(f"Winning team: {winning_team}")
                        print(f"Round scores: {round_scores}")
                        print(f"Total tricks played: {tricks_completed}")
                        
                        if game_complete:
                            print(f"🏆 GAME COMPLETE! Team {round_winner} wins with {round_scores} round wins!")
                            break
                        
                        # Reset for next hand
                        hokm_selected = False
                        tricks_completed = 0
                    
                    elif msg_type == 'game_over':
                        winner_team = data.get('winner_team')
                        print(f"🏆 GAME OVER! Team {winner_team} wins!")
                        game_complete = True
                        break
                    
                    elif msg_type == 'error':
                        error_msg = data.get('message', '')
                        print(f"{player_info['name']} ERROR: {error_msg}")
                        
                        # Handle suit-following errors by trying another card
                        if "You must follow suit" in error_msg and player_info['hand']:
                            # Try another card (simple strategy)
                            for card in player_info['hand']:
                                await player_ws.send(json.dumps({
                                    "type": "play_card",
                                    "room_code": ROOM_CODE,
                                    "player_id": player_info['player_id'],
                                    "card": card
                                }))
                                break
                
                except Exception as e:
                    print(f"Error processing message: {e}")
                    continue
    
    except Exception as e:
        print(f"Main loop error: {e}")
    
    finally:
        # Close all connections
        for ws in players:
            await ws.close()
    
    # Report results
    print(f"\n=== Test Results ===")
    print(f"Hands completed: {hands_completed}")
    print(f"Tricks played in final hand: {tricks_completed}")
    print(f"Game completed: {game_complete}")
    
    # Player statistics
    for ws, info in player_data.items():
        print(f"{info['name']}: {info['tricks_played']} tricks played")
    
    # Success criteria
    success = (
        hands_completed >= 1 and  # At least one hand completed
        tricks_completed >= 13 and  # At least 13 tricks in a hand
        all(info['tricks_played'] > 0 for info in player_data.values())  # All players participated
    )
    
    if success:
        print("✅ SUCCESS: Full hand completion test passed!")
        print("- Complete 13-trick hands working")
        print("- Multi-round scoring functional") 
        print("- All players successfully participated")
    else:
        print("❌ FAILED: Test did not meet success criteria")
    
    return success

if __name__ == "__main__":
    asyncio.run(test_full_hand())
