#!/usr/bin/env python3
"""
Test specifically for hakem disconnect/reconnect during hokm selection.
"""

import asyncio
import websockets
import json
import time
import sys
import uuid

async def test_hakem_disconnect_reconnect():
    """Test hakem disconnect/reconnect during hokm selection"""
    
    # Generate unique identifiers
    room_code = f"HAKEM{int(time.time()) % 10000}"
    
    print(f"=== TESTING HAKEM DISCONNECT/RECONNECT ===")
    print(f"Room Code: {room_code}")
    print()
    
    try:
        # Step 1: Connect all 4 players
        print("Step 1: Connecting all 4 players...")
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
            print(f"{username} join response: {response}")
            
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
        
        # Step 2: Wait for team assignment and identify hakem
        print("\nStep 2: Waiting for team assignment...")
        
        hakem_player = None
        hakem_username = None
        
        # Get team assignment from all players
        for player in players:
            try:
                # Wait for phase change and team assignment
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=5.0)
                    data = json.loads(msg)
                    print(f"{player['username']} received: {data.get('type')}")
                    
                    if data.get('type') == 'team_assignment':
                        hakem_username = data.get('hakem')
                        print(f"Hakem identified: {hakem_username}")
                        
                        # Find the hakem player - compare actual usernames from server response
                        for p in players:
                            # The server assigns usernames like "Player 1", "Player 2", etc.
                            if hakem_username == f"Player {players.index(p) + 1}":
                                hakem_player = p
                                break
                        
                        if hakem_player:
                            break
            except asyncio.TimeoutError:
                continue
            
            if hakem_player:
                break
        
        if not hakem_player:
            print("ERROR: Could not identify hakem player")
            return
        
        print(f"Hakem is: {hakem_player['username']} (ID: {hakem_player['player_id']})")
        
        # Step 3: Wait for hokm selection phase
        print("\nStep 3: Waiting for hokm selection phase...")
        
        # Clear remaining messages from all players
        for player in players:
            try:
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=0.5)
                    data = json.loads(msg)
                    if data.get('type') == 'initial_deal' and player == hakem_player:
                        print(f"Hakem received initial deal: {data.get('is_hakem')}")
            except asyncio.TimeoutError:
                pass
        
        print("=== NOW IN HOKM SELECTION PHASE ===")
        
        # Step 4: Disconnect the hakem
        print(f"\nStep 4: Disconnecting hakem ({hakem_player['username']})...")
        await hakem_player['ws'].close()
        
        # Wait for disconnect to be processed
        await asyncio.sleep(2)
        
        # Step 5: Try to reconnect hakem
        print(f"\nStep 5: Reconnecting hakem ({hakem_player['username']})...")
        
        hakem_ws_new = await websockets.connect("ws://localhost:8765")
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": hakem_player['player_id']
        }
        
        await hakem_ws_new.send(json.dumps(reconnect_msg))
        
        try:
            reconnect_response = json.loads(await asyncio.wait_for(hakem_ws_new.recv(), timeout=5.0))
            print(f"Reconnect response: {reconnect_response}")
            
            if reconnect_response.get('type') == 'error':
                print(f"RECONNECTION FAILED: {reconnect_response.get('message')}")
                
                # Check what happened to the game
                print("\n=== CHECKING GAME STATE ===")
                
                # Try to send a message from another player to see if game is still alive
                test_player = players[0] if players[0] != hakem_player else players[1]
                
                try:
                    # Send a ping or check status
                    await test_player['ws'].send(json.dumps({"type": "ping"}))
                    test_response = json.loads(await asyncio.wait_for(test_player['ws'].recv(), timeout=2.0))
                    print(f"Test player response: {test_response}")
                except:
                    print("Cannot communicate with other players - game may be cancelled")
                
            elif reconnect_response.get('type') == 'reconnect_success':
                print("RECONNECTION SUCCESS!")
                
                game_state = reconnect_response.get('game_state', {})
                print(f"Game phase after reconnect: {game_state.get('phase')}")
                print(f"Hakem after reconnect: {game_state.get('hakem')}")
                print(f"Hand after reconnect: {len(game_state.get('hand', []))} cards")
                
                # Check if we get hokm selection prompt again
                try:
                    next_msg = json.loads(await asyncio.wait_for(hakem_ws_new.recv(), timeout=3.0))
                    print(f"Next message after reconnect: {next_msg}")
                    
                    if next_msg.get('type') == 'hokm_request' or next_msg.get('message', '').find('hokm') != -1:
                        print("✓ Hakem correctly prompted for hokm selection after reconnect!")
                    else:
                        print("✗ Hakem NOT prompted for hokm selection after reconnect")
                        
                except asyncio.TimeoutError:
                    print("No immediate hokm prompt after reconnect")
            
        except asyncio.TimeoutError:
            print("TIMEOUT: No response to reconnection attempt")
        
        # Clean up
        try:
            await hakem_ws_new.close()
        except:
            pass
        
        for player in players:
            try:
                await player['ws'].close()
            except:
                pass
        
    except Exception as e:
        print(f"ERROR in test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_hakem_disconnect_reconnect())
