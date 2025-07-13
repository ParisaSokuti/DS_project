#!/usr/bin/env python3
"""
Test the specific scenario: Player disconnects before final deal, reconnects after hokm selection
"""

import asyncio
import websockets
import json
import time
import sys
import uuid

async def test_disconnect_before_final_deal():
    """Test disconnect before final deal, then reconnect after hokm selection"""
    
    room_code = f"DEAL{int(time.time()) % 10000}"
    
    print(f"=== TESTING DISCONNECT BEFORE FINAL DEAL ===")
    print(f"Room Code: {room_code}")
    print()
    
    try:
        # Step 1: Connect all 4 players
        print("Step 1: Setting up 4-player game...")
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
                'server_username': response.get('username')  # What server calls them
            })
        
        # Step 2: Get to hokm selection phase and identify hakem
        print("\nStep 2: Getting to hokm selection...")
        
        hakem_player = None
        non_hakem_player = None
        
        for player in players:
            try:
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=3.0)
                    data = json.loads(msg)
                    
                    if data.get('type') == 'team_assignment':
                        hakem_username = data.get('hakem')
                        if hakem_username == player['server_username']:
                            hakem_player = player
                        elif not non_hakem_player and hakem_username != player['server_username']:
                            non_hakem_player = player
                            
                    if data.get('type') == 'initial_deal':
                        if hakem_player and player == hakem_player:
                            print(f"✓ Hakem {hakem_player['server_username']} received initial deal: {len(data.get('hand', []))} cards")
                        break
                        
            except asyncio.TimeoutError:
                pass
        
        if not hakem_player or not non_hakem_player:
            print("ERROR: Could not identify hakem and non-hakem players")
            return
        
        print(f"✓ Hakem: {hakem_player['server_username']}")
        print(f"✓ Non-hakem to disconnect: {non_hakem_player['server_username']}")
        
        # Step 3: Disconnect non-hakem player BEFORE hokm selection
        print(f"\nStep 3: Disconnecting {non_hakem_player['server_username']} before hokm selection...")
        await non_hakem_player['ws'].close()
        
        # Wait for disconnect to be processed
        await asyncio.sleep(1)
        
        # Step 4: Hakem chooses hokm (simulating user input)
        print(f"\nStep 4: Hakem {hakem_player['server_username']} chooses hokm...")
        
        hokm_msg = {
            "type": "hokm_selected",
            "room_code": room_code,
            "suit": "hearts"
        }
        
        await hakem_player['ws'].send(json.dumps(hokm_msg))
        
        # Step 5: Collect messages from all connected players
        print(f"\nStep 5: Collecting messages after hokm selection...")
        
        messages_received = {}
        for player in players:
            if player == non_hakem_player:
                continue  # Skip disconnected player
                
            messages_received[player['server_username']] = []
            try:
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=2.0)
                    data = json.loads(msg)
                    messages_received[player['server_username']].append(data)
                    print(f"📨 {player['server_username']}: {data.get('type')}")
                    
                    if data.get('type') == 'final_deal':
                        hand_size = len(data.get('hand', []))
                        print(f"   -> Final deal: {hand_size} cards")
                        
            except asyncio.TimeoutError:
                pass
        
        # Step 6: Reconnect the disconnected player
        print(f"\nStep 6: Reconnecting {non_hakem_player['server_username']}...")
        
        reconnect_ws = await websockets.connect("ws://localhost:8765")
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": non_hakem_player['player_id']
        }
        
        await reconnect_ws.send(json.dumps(reconnect_msg))
        
        # Step 7: Check reconnection and hand size
        print(f"\nStep 7: Checking reconnection...")
        
        try:
            reconnect_response = json.loads(await asyncio.wait_for(reconnect_ws.recv(), timeout=5.0))
            print(f"Reconnect response: {reconnect_response.get('type')}")
            
            if reconnect_response.get('type') == 'reconnect_success':
                game_state = reconnect_response.get('game_state', {})
                hand = game_state.get('hand', [])
                phase = game_state.get('phase')
                
                print(f"✅ Reconnection successful")
                print(f"   Phase: {phase}")
                print(f"   Hand size: {len(hand)} cards")
                print(f"   Expected: 13 cards (after final deal)")
                
                if len(hand) == 13:
                    print("✅ CORRECT: Player has full hand after reconnection!")
                elif len(hand) == 5:
                    print("❌ PROBLEM: Player only has initial 5-card hand!")
                    print("   This means final deal wasn't applied to disconnected player")
                else:
                    print(f"⚠️  UNEXPECTED: Player has {len(hand)} cards")
                    
            else:
                print(f"❌ Reconnection failed: {reconnect_response}")
                
        except asyncio.TimeoutError:
            print("❌ TIMEOUT: No response to reconnection")
        
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
    asyncio.run(test_disconnect_before_final_deal())
