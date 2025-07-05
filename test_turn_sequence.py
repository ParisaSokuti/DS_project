#!/usr/bin/env python3
"""
Test script to verify turn sequence works correctly when hakem starts first trick.
"""

import asyncio
import websockets
import json
import time

async def test_turn_sequence():
    """Test that turns advance correctly from hakem to next players"""
    
    # Start the server first
    server_process = await asyncio.create_subprocess_exec(
        'python', 'backend/server.py',
        cwd='/Users/parisasokuti/my git repo/DS_project',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Wait for server to start
    await asyncio.sleep(2)
    
    try:
        # Create 4 player connections
        players = []
        for i in range(4):
            ws = await websockets.connect("ws://localhost:8765")
            players.append(ws)
            
            # Join room
            await ws.send(json.dumps({
                'type': 'join',
                'username': f'TestPlayer{i+1}',
                'room_code': '1234'
            }))
            
            # Read join response
            response = await ws.recv()
            print(f"Player {i+1} joined: {json.loads(response)}")
        
        # Wait for all players to join and game to start
        await asyncio.sleep(1)
        
        # Read all messages to find who the hakem is
        hakem = None
        for i, ws in enumerate(players):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=1)
                    data = json.loads(message)
                    print(f"Player {i+1} received: {data['type']}")
                    
                    if data['type'] == 'initial_deal' and data.get('is_hakem'):
                        hakem = i
                        print(f"*** Player {i+1} is the HAKEM ***")
                    
                    if data['type'] == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn')
                        print(f"Player {i+1}: Current turn is {current_player}, your turn: {your_turn}")
                        
                        # If it's hakem's turn, play a card
                        if your_turn and i == hakem:
                            hand = data.get('hand', [])
                            if hand:
                                card_to_play = hand[0]  # Play first card
                                print(f"*** HAKEM (Player {i+1}) playing card: {card_to_play} ***")
                                await ws.send(json.dumps({
                                    'type': 'play_card',
                                    'room_code': '1234',
                                    'player_id': f'test_player_{i+1}',
                                    'card': card_to_play
                                }))
                        
            except asyncio.TimeoutError:
                break
        
        # Wait for more messages after hakem plays
        await asyncio.sleep(2)
        
        # Check if turn advanced to next player
        for i, ws in enumerate(players):
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=1)
                    data = json.loads(message)
                    print(f"After hakem play - Player {i+1} received: {data['type']}")
                    
                    if data['type'] == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn')
                        print(f"*** TURN ADVANCED: Current turn is now {current_player}, Player {i+1} turn: {your_turn} ***")
            except asyncio.TimeoutError:
                break
        
        print("Test completed!")
        
    finally:
        # Clean up
        for ws in players:
            await ws.close()
        
        server_process.terminate()
        await server_process.wait()

if __name__ == "__main__":
    asyncio.run(test_turn_sequence())
