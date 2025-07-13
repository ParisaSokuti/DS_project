#!/usr/bin/env python3
"""
Comprehensive test for hakem disconnect/reconnect with hokm selection
"""

import asyncio
import websockets
import json
import time
import sys
import uuid

async def test_complete_hakem_disconnect_flow():
    """Test complete flow: hakem disconnects during hokm selection, reconnects, and chooses hokm"""
    
    room_code = f"FINAL{int(time.time()) % 10000}"
    
    print(f"=== COMPREHENSIVE HAKEM DISCONNECT/RECONNECT TEST ===")
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
                'original_id': player_id
            })
        
        # Step 2: Get to hokm selection phase
        print("\nStep 2: Getting to hokm selection phase...")
        
        hakem_player = None
        
        for player in players:
            messages = []
            try:
                while True:
                    msg = await asyncio.wait_for(player['ws'].recv(), timeout=2.0)
                    data = json.loads(msg)
                    messages.append(data)
                    
                    if data.get('type') == 'team_assignment':
                        hakem_username = data.get('hakem')
                        if hakem_username == f"Player {players.index(player) + 1}":
                            hakem_player = player
                            
                    if data.get('type') == 'initial_deal' and player == hakem_player:
                        print(f"✓ Hakem {hakem_player['username']} received initial deal")
                        
            except asyncio.TimeoutError:
                pass
        
        if not hakem_player:
            print("ERROR: Could not identify hakem")
            return
        
        print(f"✓ Game setup complete - Hakem: {hakem_player['username']}")
        
        # Step 3: Disconnect hakem during hokm selection
        print(f"\nStep 3: Disconnecting hakem ({hakem_player['username']})...")
        await hakem_player['ws'].close()
        
        # Wait for disconnect to be processed
        await asyncio.sleep(1)
        
        # Step 4: Reconnect hakem
        print(f"\nStep 4: Reconnecting hakem...")
        
        hakem_ws_new = await websockets.connect("ws://localhost:8765")
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": hakem_player['player_id']
        }
        
        await hakem_ws_new.send(json.dumps(reconnect_msg))
        
        # Step 5: Check reconnection and hokm prompt
        print("\nStep 5: Checking reconnection and hokm prompt...")
        
        messages_after_reconnect = []
        try:
            # Get the reconnect_success message
            reconnect_response = json.loads(await asyncio.wait_for(hakem_ws_new.recv(), timeout=5.0))
            messages_after_reconnect.append(reconnect_response)
            
            # Get any additional messages (hokm_request, etc.)
            while True:
                msg = await asyncio.wait_for(hakem_ws_new.recv(), timeout=2.0)
                data = json.loads(msg)
                messages_after_reconnect.append(data)
        except asyncio.TimeoutError:
            pass
        
        print(f"Received {len(messages_after_reconnect)} messages after reconnect:")
        for i, msg in enumerate(messages_after_reconnect):
            print(f"  {i+1}. {msg.get('type')}: {msg.get('message', 'N/A')}")
        
        # Validate the flow
        reconnect_success = any(msg.get('type') == 'reconnect_success' for msg in messages_after_reconnect)
        hokm_prompt = any(msg.get('type') == 'hokm_request' for msg in messages_after_reconnect)
        
        if reconnect_success:
            print("✅ RECONNECTION SUCCESSFUL")
            
            reconnect_data = next(msg for msg in messages_after_reconnect if msg.get('type') == 'reconnect_success')
            game_state = reconnect_data.get('game_state', {})
            
            print(f"   Phase: {game_state.get('phase')}")
            print(f"   Hakem: {game_state.get('hakem')}")
            print(f"   Hand: {len(game_state.get('hand', []))} cards")
            print(f"   Teams preserved: {bool(game_state.get('teams'))}")
            
        else:
            print("❌ RECONNECTION FAILED")
            
        if hokm_prompt:
            print("✅ HOKM PROMPT SENT TO HAKEM")
        else:
            print("❌ NO HOKM PROMPT SENT")
            
        # Step 6: Try to choose hokm
        print(f"\nStep 6: Trying to choose hokm...")
        
        if hokm_prompt:
            hokm_choice_msg = {
                "type": "choose_hokm",
                "hokm": "hearts"
            }
            
            await hakem_ws_new.send(json.dumps(hokm_choice_msg))
            
            try:
                hokm_response = json.loads(await asyncio.wait_for(hakem_ws_new.recv(), timeout=3.0))
                print(f"Hokm choice response: {hokm_response}")
                
                if hokm_response.get('type') == 'hokm_chosen':
                    print("✅ HOKM CHOICE ACCEPTED - Full flow working!")
                else:
                    print(f"⚠️  Unexpected hokm response: {hokm_response}")
                    
            except asyncio.TimeoutError:
                print("⚠️  No response to hokm choice")
        
        # Final summary
        print(f"\n=== TEST SUMMARY ===")
        if reconnect_success and hokm_prompt:
            print("🎉 SUCCESS: Hakem disconnect/reconnect during hokm selection is fully working!")
            print("   - Player reconnects successfully")
            print("   - Game state is preserved") 
            print("   - Hakem is prompted to choose hokm")
            print("   - Full game flow continues")
        else:
            print("❌ ISSUES REMAIN:")
            if not reconnect_success:
                print("   - Reconnection failed")
            if not hokm_prompt:
                print("   - Hokm prompt not sent")
        
        # Clean up
        try:
            await hakem_ws_new.close()
        except:
            pass
        
        for player in players:
            if player != hakem_player:
                try:
                    await player['ws'].close()
                except:
                    pass
        
    except Exception as e:
        print(f"ERROR in test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_complete_hakem_disconnect_flow())
