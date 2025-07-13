#!/usr/bin/env python3
"""
Test game continuation after player disconnect/reconnect during hokm selection
"""

import asyncio
import websockets
import json
import time
import sys
import uuid

async def test_game_continuation():
    """Test that game continues properly after disconnect/reconnect"""
    
    room_code = f"CONT{int(time.time()) % 10000}"
    
    print(f"=== TESTING GAME CONTINUATION AFTER DISCONNECT/RECONNECT ===")
    print(f"Room Code: {room_code}")
    print()
    
    try:
        # Step 1: Connect all 4 players
        print("Step 1: Setting up 4-player game...")
        players = []
        
        for i in range(4):
            username = f"Player{i+1}"
            
            ws = await websockets.connect("ws://localhost:8765")
            join_msg = {
                "type": "join",
                "room_code": room_code,
                "username": username,
                "player_id": str(uuid.uuid4())
            }
            
            await ws.send(json.dumps(join_msg))
            response = json.loads(await ws.recv())
            
            if response.get('type') != 'join_success':
                print(f"Failed to join room for {username}")
                return
            
            players.append({
                'ws': ws,
                'username': username,
                'player_id': response.get('player_id'),
                'server_username': response.get('username')
            })
        
        # Step 2: Progress to hokm selection and find hakem
        print("\nStep 2: Progressing to hokm selection...")
        
        hakem_player = None
        non_hakem_player = players[0]  # Default to first player as non-hakem
        
        for player in players:
            try:
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=3.0)
                    data = json.loads(msg)
                    
                    if data.get('type') == 'team_assignment':
                        hakem_username = data.get('hakem')
                        for p in players:
                            if p['server_username'] == hakem_username:
                                hakem_player = p
                            elif p['server_username'] != hakem_username and p != hakem_player:
                                non_hakem_player = p
                                
                    if data.get('type') == 'initial_deal':
                        if player == hakem_player:
                            print(f"✓ Hakem {hakem_player['server_username']} ready to choose hokm")
                        break
                        
            except asyncio.TimeoutError:
                pass
        
        if not hakem_player:
            print("ERROR: Could not identify hakem")
            return
        
        print(f"✓ Hakem: {hakem_player['server_username']}")
        print(f"✓ Will disconnect: {non_hakem_player['server_username']}")
        
        # Step 3: Disconnect non-hakem player
        print(f"\nStep 3: Disconnecting {non_hakem_player['server_username']}...")
        await non_hakem_player['ws'].close()
        await asyncio.sleep(1)
        
        # Step 4: Hakem chooses hokm
        print(f"\nStep 4: Hakem chooses hokm...")
        hokm_msg = {
            "type": "hokm_selected",
            "room_code": room_code,
            "suit": "hearts"
        }
        
        await hakem_player['ws'].send(json.dumps(hokm_msg))
        
        # Step 5: Collect messages from connected players
        print(f"\nStep 5: Collecting post-hokm messages...")
        
        post_hokm_messages = []
        for player in players:
            if player == non_hakem_player:
                continue  # Skip disconnected player
                
            try:
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=2.0)
                    data = json.loads(msg)
                    post_hokm_messages.append((player['server_username'], data))
                    print(f"📨 {player['server_username']}: {data.get('type')}")
                    
                    if data.get('type') == 'final_deal':
                        hand_size = len(data.get('hand', []))
                        print(f"   -> Hand size: {hand_size}")
                    elif data.get('type') == 'turn_start':
                        current_player = data.get('current_player')
                        your_turn = data.get('your_turn', False)
                        print(f"   -> Turn: {current_player}, Your turn: {your_turn}")
                        
            except asyncio.TimeoutError:
                break
        
        # Step 6: Reconnect the disconnected player
        print(f"\nStep 6: Reconnecting {non_hakem_player['server_username']}...")
        
        reconnect_ws = await websockets.connect("ws://localhost:8765")
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": non_hakem_player['player_id']
        }
        
        await reconnect_ws.send(json.dumps(reconnect_msg))
        
        # Step 7: Check what reconnected player receives
        print(f"\nStep 7: Checking reconnection messages...")
        
        reconnect_messages = []
        try:
            while True:
                msg = await asyncio.wait_for(reconnect_ws.recv(), timeout=3.0)
                data = json.loads(msg)
                reconnect_messages.append(data)
                print(f"📨 Reconnect: {data.get('type')}")
                
                if data.get('type') == 'reconnect_success':
                    game_state = data.get('game_state', {})
                    hand_size = len(game_state.get('hand', []))
                    phase = game_state.get('phase')
                    print(f"   -> Phase: {phase}, Hand: {hand_size} cards")
                    
                elif data.get('type') == 'final_deal':
                    hand_size = len(data.get('hand', []))
                    print(f"   -> Final deal: {hand_size} cards")
                    
                elif data.get('type') == 'turn_start':
                    current_player = data.get('current_player')
                    your_turn = data.get('your_turn', False)
                    hand_size = len(data.get('hand', []))
                    print(f"   -> Turn start: {current_player}, Your turn: {your_turn}, Hand: {hand_size} cards")
                    
        except asyncio.TimeoutError:
            pass
        
        # Analysis
        print(f"\n=== ANALYSIS ===")
        
        has_final_deal = any(msg.get('type') == 'final_deal' for _, msg in post_hokm_messages)
        has_turn_start = any(msg.get('type') == 'turn_start' for _, msg in post_hokm_messages)
        
        reconnect_has_final_deal = any(msg.get('type') == 'final_deal' for msg in reconnect_messages)
        reconnect_has_turn_start = any(msg.get('type') == 'turn_start' for msg in reconnect_messages)
        
        print(f"Connected players received:")
        print(f"  ✓ Final deal: {has_final_deal}")
        print(f"  ✓ Turn start: {has_turn_start}")
        
        print(f"Reconnected player received:")
        print(f"  ✓ Final deal: {reconnect_has_final_deal}")
        print(f"  ✓ Turn start: {reconnect_has_turn_start}")
        
        if has_final_deal and has_turn_start and (reconnect_has_final_deal or reconnect_has_turn_start):
            print("\n🎉 SUCCESS: Game progression working correctly!")
            print("   - Final deal completed")
            print("   - First trick started") 
            print("   - Reconnected player caught up")
        else:
            print("\n❌ ISSUES DETECTED:")
            if not has_final_deal:
                print("   - Connected players didn't receive final deal")
            if not has_turn_start:
                print("   - Game didn't progress to first trick")
            if not reconnect_has_final_deal and not reconnect_has_turn_start:
                print("   - Reconnected player not properly caught up")
        
        # Clean up
        try:
            await reconnect_ws.close()
        except:
            pass
        
        for player in players:
            if player != non_hakem_player:
                try:
                    await player['ws'].close()
                except:
                    pass
        
    except Exception as e:
        print(f"ERROR in test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_game_continuation())
