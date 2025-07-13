#!/usr/bin/env python3
"""
Test script to reproduce the reconnection issue and verify the fix.
This simulates the exact scenario described by the user.
"""

import asyncio
import json
import websockets
import sys

async def test_reconnection_scenario():
    """Test the reconnection scenario described by the user"""
    
    print("=== Testing Reconnection Scenario ===")
    print("1. Starting 4 players to create a full game")
    print("2. One player will disconnect and reconnect")
    print("3. Verify they can continue playing")
    
    # Connect 4 players
    players = []
    for i, username in enumerate(["nima", "kasra", "parisa1", "arvin"]):
        try:
            print(f"\n🔌 Connecting {username}...")
            ws = await websockets.connect("ws://localhost:8765")
            
            # Login
            await ws.send(json.dumps({
                "type": "login",
                "username": username,
                "password": "test123"
            }))
            
            # Wait for auth response
            response = await ws.recv()
            auth_data = json.loads(response)
            
            if auth_data.get("success"):
                print(f"✅ {username} authenticated")
                player_id = auth_data.get("player_id")
                
                # Join room
                await ws.send(json.dumps({
                    "type": "join",
                    "room_code": "9999"
                }))
                
                # Wait for join response
                response = await ws.recv()
                join_data = json.loads(response)
                
                if join_data.get("type") == "join_success":
                    print(f"✅ {username} joined room")
                    players.append((username, ws, player_id))
                else:
                    print(f"❌ {username} failed to join room")
                    
            else:
                print(f"❌ {username} authentication failed")
                
        except Exception as e:
            print(f"❌ Error connecting {username}: {e}")
    
    if len(players) < 4:
        print("❌ Not enough players connected")
        return
    
    print(f"\n✅ All 4 players connected successfully!")
    
    # Listen for game events for a while
    print("\n📋 Listening for game events...")
    
    try:
        # Listen for game progression
        for i in range(20):  # Listen for 20 messages
            for username, ws, player_id in players:
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=0.1)
                    data = json.loads(response)
                    msg_type = data.get("type")
                    
                    if msg_type == "team_assignment":
                        print(f"🎯 Teams assigned!")
                        teams = data.get("teams", {})
                        print(f"   Team 1: {teams.get('1', [])}")
                        print(f"   Team 2: {teams.get('2', [])}")
                        
                    elif msg_type == "phase_change":
                        phase = data.get("new_phase")
                        print(f"🔄 Phase changed to: {phase}")
                        
                    elif msg_type == "initial_deal":
                        print(f"🎴 {username} received initial deal")
                        
                    elif msg_type == "turn_start":
                        current_player = data.get("current_player")
                        your_turn = data.get("your_turn")
                        print(f"🎮 Turn: {current_player} (your turn: {your_turn})")
                        
                        # If it's this player's turn, simulate disconnect/reconnect
                        if your_turn and username == "parisa1":
                            print(f"\n🔌 Simulating disconnect for {username}...")
                            await ws.close()
                            
                            # Wait a moment
                            await asyncio.sleep(2)
                            
                            # Reconnect
                            print(f"🔄 Reconnecting {username}...")
                            new_ws = await websockets.connect("ws://localhost:8765")
                            
                            # Re-authenticate
                            await new_ws.send(json.dumps({
                                "type": "login",
                                "username": username,
                                "password": "test123"
                            }))
                            
                            auth_response = await new_ws.recv()
                            auth_data = json.loads(auth_response)
                            
                            if auth_data.get("success"):
                                print(f"✅ {username} re-authenticated")
                                
                                # Try to reconnect to game
                                await new_ws.send(json.dumps({
                                    "type": "reconnect",
                                    "player_id": player_id,
                                    "room_code": "9999"
                                }))
                                
                                # Wait for reconnect response
                                reconnect_response = await new_ws.recv()
                                reconnect_data = json.loads(reconnect_response)
                                
                                if reconnect_data.get("type") == "reconnect_success":
                                    print(f"✅ {username} reconnected successfully!")
                                    game_state = reconnect_data.get("game_state", {})
                                    print(f"📋 Game state: {game_state.get('phase')}")
                                    
                                    # Update player connection
                                    players[2] = (username, new_ws, player_id)
                                    
                                    # Wait for turn_start after reconnection
                                    turn_response = await new_ws.recv()
                                    turn_data = json.loads(turn_response)
                                    
                                    if turn_data.get("type") == "turn_start":
                                        print(f"🎮 Received turn_start after reconnection!")
                                        your_turn_after = turn_data.get("your_turn")
                                        print(f"   Your turn: {your_turn_after}")
                                        
                                        if your_turn_after:
                                            print(f"✅ SUCCESS: {username} can continue playing after reconnection!")
                                        else:
                                            print(f"ℹ️  Not your turn after reconnection")
                                    else:
                                        print(f"❌ Expected turn_start after reconnection, got: {turn_data.get('type')}")
                                        
                                else:
                                    print(f"❌ {username} reconnection failed: {reconnect_data.get('message')}")
                            else:
                                print(f"❌ {username} re-authentication failed")
                                
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"❌ Error with {username}: {e}")
                    continue
                    
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted")
    
    # Clean up
    print("\n🧹 Cleaning up...")
    for username, ws, player_id in players:
        try:
            await ws.close()
        except:
            pass
            
    print("✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_reconnection_scenario())
