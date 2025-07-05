#!/usr/bin/env python3
"""
Test script to reproduce the hokm selection reconnection bug
"""

import asyncio
import websockets
import json
import time

SERVER_URI = "ws://localhost:8765"

async def simulate_hokm_reconnection_bug():
    """Simulate the exact scenario that causes the hokm selection bug"""
    
    print("🐛 Reproducing hokm selection reconnection bug")
    print("=" * 60)
    
    # Clear Redis to start fresh
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.flushall()
        print("🧹 Redis cleared")
    except:
        print("⚠️  Could not clear Redis (continuing anyway)")
    
    # Step 1: Connect 4 players
    print("\n=== Step 1: Connect 4 players ===")
    
    players = []
    for i in range(1, 5):
        try:
            ws = await websockets.connect(SERVER_URI)
            await ws.send(json.dumps({
                "type": "join",
                "username": f"Player{i}",
                "room_code": "9999"
            }))
            
            response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = json.loads(response_raw)
            
            if response.get('type') == 'join_success':
                player_info = {
                    'id': i,
                    'ws': ws,
                    'player_id': response.get('player_id'),
                    'username': response.get('username'),
                    'player_number': response.get('player_number')
                }
                players.append(player_info)
                print(f"✅ {player_info['username']} connected")
            else:
                print(f"❌ Player {i} failed to connect: {response}")
                await ws.close()
                
        except Exception as e:
            print(f"❌ Player {i} connection error: {e}")
    
    if len(players) != 4:
        print(f"❌ Not enough players connected ({len(players)}/4). Aborting test.")
        return False
    
    # Step 2: Wait for game to reach hokm selection phase
    print(f"\n=== Step 2: Wait for hokm selection phase ===")
    
    hakem_player = None
    
    # Listen for messages to find who the hakem is
    for player in players:
        try:
            while True:
                msg_raw = await asyncio.wait_for(player['ws'].recv(), timeout=10.0)
                msg = json.loads(msg_raw)
                print(f"📨 {player['username']}: {msg.get('type')} - {msg.get('message', '')}")
                
                if msg.get('type') == 'team_assignment':
                    hakem = msg.get('hakem')
                    if hakem == player['username']:
                        hakem_player = player
                        print(f"🎯 {player['username']} is the hakem")
                
                if msg.get('type') == 'initial_deal':
                    print(f"🃏 {player['username']} received initial hand")
                
                if msg.get('type') in ['hokm_selection_prompt', 'waiting_for_hokm']:
                    print(f"⏳ Hokm selection phase reached for {player['username']}")
                    break
                    
        except asyncio.TimeoutError:
            print(f"⏰ Timeout waiting for messages for {player['username']}")
            break
        except Exception as e:
            print(f"❌ Error reading messages for {player['username']}: {e}")
            break
    
    if not hakem_player:
        print("❌ Could not identify hakem player. Aborting test.")
        return False
    
    print(f"✅ Game reached hokm selection phase. Hakem: {hakem_player['username']}")
    
    # Step 3: Disconnect the hakem
    print(f"\n=== Step 3: Disconnect hakem ({hakem_player['username']}) ===")
    
    await hakem_player['ws'].close()
    print(f"🔌 {hakem_player['username']} disconnected")
    
    # Give server time to detect disconnect
    await asyncio.sleep(3)
    
    # Step 4: Check what other players see
    print(f"\n=== Step 4: Check game state after disconnect ===")
    
    remaining_players = [p for p in players if p != hakem_player]
    
    for player in remaining_players:
        try:
            # Check if there are pending messages
            while True:
                try:
                    msg_raw = await asyncio.wait_for(player['ws'].recv(), timeout=1.0)
                    msg = json.loads(msg_raw)
                    print(f"📨 {player['username']}: {msg.get('type')} - {msg.get('message', '')}")
                    
                    if msg.get('type') == 'game_cancelled':
                        print(f"🚫 Game was cancelled after hakem disconnect!")
                        return False
                        
                except asyncio.TimeoutError:
                    break
        except Exception as e:
            print(f"❌ Error checking messages for {player['username']}: {e}")
    
    # Step 5: Reconnect the hakem
    print(f"\n=== Step 5: Reconnect hakem ===")
    
    try:
        new_ws = await websockets.connect(SERVER_URI)
        await new_ws.send(json.dumps({
            "type": "reconnect",
            "player_id": hakem_player['player_id'],
            "room_code": "9999"
        }))
        
        response_raw = await asyncio.wait_for(new_ws.recv(), timeout=5.0)
        response = json.loads(response_raw)
        
        print(f"📥 Reconnection response: {response.get('type')} - {response.get('message', '')}")
        
        if response.get('type') == 'reconnect_success':
            hakem_player['ws'] = new_ws
            print(f"✅ {hakem_player['username']} reconnected successfully")
        else:
            print(f"❌ Reconnection failed: {response}")
            return False
            
    except Exception as e:
        print(f"❌ Reconnection error: {e}")
        return False
    
    # Step 6: Try to select hokm
    print(f"\n=== Step 6: Try hokm selection ===")
    
    try:
        await hakem_player['ws'].send(json.dumps({
            "type": "hokm_selected",
            "room_code": "9999",
            "suit": "hearts"
        }))
        
        # Wait for response
        response_raw = await asyncio.wait_for(hakem_player['ws'].recv(), timeout=5.0)
        response = json.loads(response_raw)
        
        print(f"📥 Hokm selection response: {response.get('type')} - {response.get('message', '')}")
        
        if response.get('type') == 'error' and 'Game not found' in response.get('message', ''):
            print(f"🐛 BUG REPRODUCED: Game not found for hokm selection!")
            return False
        elif response.get('type') == 'hokm_selected':
            print(f"✅ Hokm selection successful after reconnection!")
            return True
        else:
            print(f"⚠️  Unexpected response: {response}")
            return False
            
    except Exception as e:
        print(f"❌ Hokm selection error: {e}")
        return False
    
    finally:
        # Cleanup
        print(f"\n🧹 Cleaning up connections...")
        for player in players:
            try:
                if not player['ws'].closed:
                    await player['ws'].close()
            except:
                pass

async def main():
    """Main test runner"""
    print("🧪 Hokm Selection Reconnection Bug Test")
    print("=" * 50)
    
    try:
        success = await simulate_hokm_reconnection_bug()
        
        if success:
            print(f"\n✅ Bug is fixed! Hokm selection works after reconnection.")
        else:
            print(f"\n❌ Bug still exists! Hokm selection fails after reconnection.")
        
        return success
        
    except Exception as e:
        print(f"\n💥 Test crashed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        exit(130)
