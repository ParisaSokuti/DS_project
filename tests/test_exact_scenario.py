#!/usr/bin/env python3
"""
Test to reproduce the exact user scenario:
1. Players in game reach hokm selection
2. One player reconnects 
3. Hokm selection fails with "Game not found"
"""

import asyncio
import websockets
import json
import redis

SERVER_URI = "ws://localhost:8765"

async def test_exact_user_scenario():
    """Reproduce the exact scenario the user reported"""
    
    print("🎭 Reproducing Exact User Scenario")
    print("=" * 50)
    
    # Clear state
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.flushall()
        print("🧹 Redis cleared")
    except:
        pass
    
    players = []
    
    # Step 1: Connect 4 players to fill the room
    print("\n=== Step 1: Connect 4 players ===")
    
    for i in range(1, 5):
        try:
            ws = await websockets.connect(SERVER_URI)
            
            # Send join message
            await ws.send(json.dumps({
                "type": "join",
                "username": f"Player{i}",
                "room_code": "9999"
            }))
            
            # Get response
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            response_data = json.loads(response)
            
            if response_data.get('type') == 'join_success':
                player_info = {
                    'id': i,
                    'ws': ws,
                    'player_id': response_data.get('player_id'),
                    'username': response_data.get('username'),
                    'player_number': response_data.get('player_number')
                }
                players.append(player_info)
                print(f"✅ Player {i} connected as {player_info['username']}")
            else:
                print(f"❌ Player {i} failed: {response_data}")
                await ws.close()
                
        except Exception as e:
            print(f"❌ Player {i} error: {e}")
    
    if len(players) != 4:
        print(f"❌ Expected 4 players, got {len(players)}")
        return False
    
    # Step 2: Let the game progress to hokm selection
    print(f"\n=== Step 2: Progress to hokm selection ===")
    
    hakem_player = None
    
    # Read messages to find hakem and reach hokm phase
    for i in range(10):  # Read up to 10 messages per player
        for player in players:
            try:
                msg = await asyncio.wait_for(player['ws'].recv(), timeout=2)
                msg_data = json.loads(msg)
                msg_type = msg_data.get('type', '')
                
                print(f"📨 {player['username']}: {msg_type}")
                
                if msg_type == 'team_assignment':
                    hakem = msg_data.get('hakem')
                    if hakem == player['username']:
                        hakem_player = player
                        print(f"🎯 {player['username']} is the hakem")
                
                elif msg_type == 'hokm_selection_prompt':
                    print(f"🎮 {player['username']} can select hokm")
                    
                elif msg_type == 'waiting_for_hokm':
                    print(f"⏳ {player['username']} waiting for hokm")
                    
            except asyncio.TimeoutError:
                continue  # No more messages for this player
            except Exception as e:
                print(f"❌ Error reading {player['username']}: {e}")
    
    if not hakem_player:
        print("❌ Could not identify hakem. Test incomplete.")
        return False
    
    print(f"✅ Game ready. Hakem: {hakem_player['username']}")
    
    # Step 3: Simulate Player 4 disconnecting and reconnecting
    print(f"\n=== Step 3: Player 4 disconnect and reconnect ===")
    
    player4 = players[3]  # Player 4
    player4_id = player4['player_id']
    
    # Close Player 4 connection
    await player4['ws'].close()
    print(f"🔌 {player4['username']} disconnected")
    
    # Wait a moment for server to detect
    await asyncio.sleep(2)
    
    # Check what other players see
    print("📡 Checking messages from other players...")
    for player in players[:3]:  # First 3 players
        try:
            while True:
                msg = await asyncio.wait_for(player['ws'].recv(), timeout=1)
                msg_data = json.loads(msg)
                print(f"📨 {player['username']}: {msg_data.get('type')} - {msg_data.get('message', '')}")
                
                if msg_data.get('type') == 'game_cancelled':
                    print("🚫 PROBLEM: Game was cancelled after disconnect!")
                    return False
        except asyncio.TimeoutError:
            break
    
    # Reconnect Player 4
    print(f"🔄 Reconnecting {player4['username']}...")
    
    try:
        new_ws = await websockets.connect(SERVER_URI)
        await new_ws.send(json.dumps({
            "type": "reconnect",
            "player_id": player4_id,
            "room_code": "9999"
        }))
        
        response = await asyncio.wait_for(new_ws.recv(), timeout=5)
        response_data = json.loads(response)
        
        print(f"📥 Reconnection response: {response_data.get('type')}")
        
        if response_data.get('type') != 'reconnect_success':
            print(f"❌ Reconnection failed: {response_data}")
            return False
        
        player4['ws'] = new_ws
        print(f"✅ {player4['username']} reconnected")
        
    except Exception as e:
        print(f"❌ Reconnection error: {e}")
        return False
    
    # Step 4: Check what messages other players got about reconnection
    print(f"\n=== Step 4: Check reconnection messages ===")
    
    for player in players[:3]:  # First 3 players
        try:
            while True:
                msg = await asyncio.wait_for(player['ws'].recv(), timeout=1)
                msg_data = json.loads(msg)
                print(f"📨 {player['username']}: {msg_data.get('type')} - {msg_data.get('message', '')}")
        except asyncio.TimeoutError:
            break
    
    # Step 5: Try hokm selection (this is where the bug occurs)
    print(f"\n=== Step 5: Hakem tries hokm selection ===")
    
    try:
        await hakem_player['ws'].send(json.dumps({
            "type": "hokm_selected",
            "room_code": "9999",
            "suit": "hearts"
        }))
        
        response = await asyncio.wait_for(hakem_player['ws'].recv(), timeout=5)
        response_data = json.loads(response)
        
        print(f"📥 Hokm response: {response_data.get('type')} - {response_data.get('message', '')}")
        
        if 'Game not found' in response_data.get('message', ''):
            print("🐛 BUG REPRODUCED: Game not found for hokm selection!")
            return False
        elif response_data.get('type') == 'hokm_selected':
            print("✅ SUCCESS: Hokm selection worked after reconnection!")
            return True
        else:
            print(f"⚠️  Unexpected response: {response_data}")
            return False
            
    except Exception as e:
        print(f"❌ Hokm selection error: {e}")
        return False
    
    finally:
        # Cleanup
        for player in players:
            try:
                if not player['ws'].closed:
                    await player['ws'].close()
            except:
                pass

async def main():
    try:
        print("Testing the exact user scenario...")
        success = await test_exact_user_scenario()
        
        if success:
            print(f"\n✅ BUG IS FIXED! Hokm selection works after reconnection.")
        else:
            print(f"\n❌ BUG STILL EXISTS! Hokm selection fails after reconnection.")
        
        return success
        
    except Exception as e:
        print(f"💥 Test crashed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(main())
