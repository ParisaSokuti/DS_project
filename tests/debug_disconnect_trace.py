#!/usr/bin/env python3
"""
Debug script to trace player disconnect/reconnect during hokm selection.
This will help us understand exactly why "Player not found in room" occurs.
"""

import asyncio
import websockets
import json
import time
import sys
import uuid

async def test_disconnect_reconnect_trace():
    """Test disconnect/reconnect with detailed tracing"""
    
    # Generate unique identifiers
    room_code = f"TEST{int(time.time()) % 10000}"
    player_id = str(uuid.uuid4())
    username = f"TestPlayer_{int(time.time()) % 1000}"
    
    print(f"=== STARTING DISCONNECT/RECONNECT TRACE TEST ===")
    print(f"Room Code: {room_code}")
    print(f"Player ID: {player_id}")
    print(f"Username: {username}")
    print()
    
    try:
        # Step 1: Connect first player (hakem)
        print("Step 1: Connecting first player...")
        ws1 = await websockets.connect("ws://localhost:8765")
        
        join_msg = {
            "type": "join",
            "room_code": room_code,
            "username": username,
            "player_id": player_id
        }
        
        await ws1.send(json.dumps(join_msg))
        response1 = json.loads(await ws1.recv())
        print(f"Join response: {response1}")
        
        # Extract the actual player_id assigned by the server
        actual_player_id = response1.get('player_id', player_id)
        print(f"Server assigned player_id: {actual_player_id}")
        
        if response1.get('type') != 'join_success':
            print("Failed to join room")
            return
        
        # Step 2: Connect remaining players to fill room
        print("\nStep 2: Connecting remaining players...")
        other_players = []
        
        for i in range(3):  # Need 3 more players for a 4-player room
            username_other = f"Player{i+2}_{int(time.time()) % 1000}"
            player_id_other = str(uuid.uuid4())
            
            ws_other = await websockets.connect("ws://localhost:8765")
            join_msg_other = {
                "type": "join",
                "room_code": room_code,
                "username": username_other,
                "player_id": player_id_other
            }
            
            await ws_other.send(json.dumps(join_msg_other))
            response_other = json.loads(await ws_other.recv())
            print(f"Player {i+2} join response: {response_other}")
            
            other_players.append({
                'ws': ws_other,
                'username': username_other,
                'player_id': player_id_other
            })
        
        # Step 3: Wait for team assignment and hokm selection phase
        print("\nStep 3: Waiting for game to start and hokm selection...")
        
        # Consume all messages until we reach hokm selection
        waiting_for_hokm = False
        while not waiting_for_hokm:
            try:
                # Check messages from first player
                msg = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                data = json.loads(msg)
                print(f"Player 1 received: {data.get('type')} - {data}")
                
                if data.get('type') == 'phase_change' and data.get('new_phase') == 'hokm_selection':
                    waiting_for_hokm = True
                    break
                
                # Also check if we received initial_deal with is_hakem=True
                if data.get('type') == 'initial_deal' and data.get('is_hakem'):
                    waiting_for_hokm = True
                    break
                
            except asyncio.TimeoutError:
                print("Timeout waiting for hokm phase")
                break
        
        # Consume messages from other players too
        for player in other_players:
            try:
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=0.1)
                    data = json.loads(msg)
                    print(f"{player['username']} received: {data.get('type')}")
            except asyncio.TimeoutError:
                break
        
        if not waiting_for_hokm:
            print("ERROR: Never reached hokm selection phase")
            return
        
        print(f"\n=== REACHED HOKM SELECTION PHASE ===")
        
        # Step 4: Disconnect the hakem player
        print(f"\nStep 4: Disconnecting hakem player ({username})...")
        await ws1.close()
        
        # Wait a moment for disconnect to be processed
        await asyncio.sleep(1)
        
        # Step 5: Try to reconnect
        print(f"\nStep 5: Attempting to reconnect player ({username})...")
        
        ws1_new = await websockets.connect("ws://localhost:8765")
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": actual_player_id  # Use the server-assigned player_id
        }
        
        await ws1_new.send(json.dumps(reconnect_msg))
        
        try:
            reconnect_response = json.loads(await asyncio.wait_for(ws1_new.recv(), timeout=5.0))
            print(f"Reconnect response: {reconnect_response}")
            
            if reconnect_response.get('type') == 'error':
                print(f"RECONNECTION FAILED: {reconnect_response.get('message')}")
                
                # This is where we need to investigate what happened
                print("\n=== INVESTIGATING FAILURE ===")
                print("The reconnection failed. This suggests the player was removed from the room")
                print("instead of being marked as disconnected.")
                
            elif reconnect_response.get('type') == 'reconnect_success':
                print("RECONNECTION SUCCESS!")
                
                # Check if we get hokm_request again
                try:
                    next_msg = json.loads(await asyncio.wait_for(ws1_new.recv(), timeout=2.0))
                    print(f"After reconnect: {next_msg}")
                except asyncio.TimeoutError:
                    print("No immediate message after reconnect")
            
        except asyncio.TimeoutError:
            print("TIMEOUT: No response to reconnection attempt")
        
        # Clean up
        try:
            await ws1_new.close()
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
    asyncio.run(test_disconnect_reconnect_trace())
