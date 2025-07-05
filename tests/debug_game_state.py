#!/usr/bin/env python3
"""
Debug script to trace what happens to game state during disconnect/reconnect
"""

import asyncio
import websockets
import json
import time
import sys
import uuid

async def test_game_state_preservation():
    """Test if game state is preserved during hakem disconnect"""
    
    # Generate unique identifiers
    room_code = f"DEBUG{int(time.time()) % 10000}"
    
    print(f"=== TESTING GAME STATE PRESERVATION ===")
    print(f"Room Code: {room_code}")
    print()
    
    try:
        # Step 1: Connect all 4 players and start game
        print("Step 1: Setting up full game...")
        players = []
        
        for i in range(4):
            username = f"Player{i+1}"
            player_id = str(uuid.uuid4())
            
            ws = await websockets.connect("ws://localhost:8765")
            join_msg = {
                "type": "join",
                "room_code": room_code,
                "username": username,
                "player_id": player_id
            }
            
            await ws.send(json.dumps(join_msg))
            response = json.loads(await ws.recv())
            
            if response.get('type') != 'join_success':
                print(f"Failed to join room for {username}")
                return
            
            actual_player_id = response.get('player_id')
            players.append({
                'ws': ws,
                'username': username,
                'player_id': actual_player_id,
                'original_id': player_id
            })
        
        # Step 2: Collect all game initialization messages
        print("\nStep 2: Collecting game initialization...")
        
        hakem_player = None
        
        for player in players:
            messages = []
            try:
                # Collect all messages for this player
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=2.0)
                    data = json.loads(msg)
                    messages.append(data)
                    
                    if data.get('type') == 'team_assignment':
                        hakem_username = data.get('hakem')
                        if hakem_username == f"Player {players.index(player) + 1}":
                            hakem_player = player
                            print(f"Hakem identified: {hakem_player['username']}")
                    
                    if data.get('type') == 'initial_deal' and data.get('is_hakem'):
                        print(f"Hakem {player['username']} received hand: {len(data.get('hand', []))} cards")
                        
            except asyncio.TimeoutError:
                pass
            
            print(f"{player['username']} received {len(messages)} messages during setup")
        
        if not hakem_player:
            print("ERROR: Could not identify hakem")
            return
        
        print(f"\n=== GAME FULLY INITIALIZED ===")
        print(f"Hakem: {hakem_player['username']}")
        
        # Step 3: Now disconnect the hakem and immediately check what happens
        print(f"\nStep 3: Disconnecting hakem and checking game state...")
        
        # Before disconnect, try to query the server about the room
        print("Before disconnect - checking if we can still communicate with server...")
        
        # Disconnect hakem
        await hakem_player['ws'].close()
        print("Hakem disconnected")
        
        # Wait a moment for server to process the disconnect
        await asyncio.sleep(1)
        
        # Step 4: Check if other players receive any messages
        print("\nStep 4: Checking messages from other players after hakem disconnect...")
        
        other_players = [p for p in players if p != hakem_player]
        
        for player in other_players:
            try:
                # Check if player receives any messages about the disconnect
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=1.0)
                    data = json.loads(msg)
                    print(f"{player['username']} received after disconnect: {data}")
                    
                    if data.get('type') == 'game_cancelled':
                        print("❌ GAME WAS CANCELLED!")
                        print("This explains why game state is lost!")
                        return
                    elif data.get('type') == 'player_disconnected':
                        print(f"✓ Player disconnect notification received by {player['username']}")
                        
            except asyncio.TimeoutError:
                print(f"{player['username']}: No messages received")
                
        print("\n=== GAME STILL ACTIVE, ATTEMPTING RECONNECT ===")
        
        # Step 5: Try to reconnect hakem
        print(f"\nStep 5: Reconnecting hakem...")
        
        hakem_ws_new = await websockets.connect("ws://localhost:8765")
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": hakem_player['player_id']
        }
        
        await hakem_ws_new.send(json.dumps(reconnect_msg))
        
        try:
            reconnect_response = json.loads(await asyncio.wait_for(hakem_ws_new.recv(), timeout=5.0))
            print(f"Reconnect response: {reconnect_response}")
            
            if reconnect_response.get('type') == 'reconnect_success':
                game_state = reconnect_response.get('game_state', {})
                print(f"✓ Reconnection successful!")
                print(f"  Phase: {game_state.get('phase')}")
                print(f"  Teams: {game_state.get('teams')}")
                print(f"  Hakem: {game_state.get('hakem')}")
                print(f"  Hand: {len(game_state.get('hand', []))} cards")
                
                if game_state.get('phase') == 'waiting':
                    print("❌ GAME STATE WAS RESET - This is the bug!")
                else:
                    print("✓ Game state preserved correctly")
                    
            else:
                print(f"❌ Reconnection failed: {reconnect_response}")
            
        except asyncio.TimeoutError:
            print("❌ TIMEOUT: No response to reconnection")
        
        # Clean up
        try:
            await hakem_ws_new.close()
        except:
            pass
        
        for player in other_players:
            try:
                await player['ws'].close()
            except:
                pass
        
    except Exception as e:
        print(f"ERROR in test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_game_state_preservation())
