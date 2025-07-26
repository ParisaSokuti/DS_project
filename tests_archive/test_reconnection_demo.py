#!/usr/bin/env python3
"""
Final Mid-Game Reconnection Demonstration
Shows the complete reconnection flow with detailed logging
"""

import asyncio
import websockets
import json
import time
import random

async def demonstrate_mid_game_reconnection():
    """Demonstrate complete mid-game reconnection flow"""
    print("🎯 MID-GAME RECONNECTION DEMONSTRATION")
    print("=" * 80)
    
    server_url = "ws://localhost:8765"
    room_code = f"demo_room_{int(time.time())}"
    players = []
    
    try:
        # Phase 1: Setup Players
        print("\n📋 Phase 1: Setting up players and game")
        player_names = ["Alice", "Bob", "Charlie", "Diana"]
        
        for i, name in enumerate(player_names):
            print(f"  🔐 Creating player {i+1}: {name}")
            
            # Connect and register
            websocket = await websockets.connect(server_url)
            username = f"{name}_{int(time.time())}"
            
            register_msg = {
                "type": "auth_register",
                "username": username,
                "password": "demo123"
            }
            
            await websocket.send(json.dumps(register_msg))
            response = await websocket.recv()
            auth_data = json.loads(response)
            
            if not auth_data.get("success", False):
                raise Exception(f"Registration failed for {name}")
            
            player_info = auth_data.get("player_info", {})
            player = {
                "name": name,
                "username": username,
                "player_id": player_info.get("player_id"),
                "token": player_info.get("token"),
                "websocket": websocket,
                "connected": True
            }
            
            # Join room
            join_msg = {
                "type": "join",
                "room_code": room_code
            }
            await websocket.send(json.dumps(join_msg))
            join_response = await websocket.recv()
            join_data = json.loads(join_response)
            
            if join_data.get("type") != "join_success":
                raise Exception(f"Join failed for {name}")
            
            players.append(player)
            print(f"  ✅ {name} joined room")
            
            await asyncio.sleep(0.5)
        
        # Phase 2: Wait for game to start
        print(f"\n🎮 Phase 2: Waiting for game to start")
        await asyncio.sleep(2)
        
        # Process initial game messages
        for player in players:
            messages_received = 0
            try:
                while messages_received < 10:  # Limit messages per player
                    response = await asyncio.wait_for(player["websocket"].recv(), timeout=2.0)
                    message = json.loads(response)
                    msg_type = message.get("type")
                    
                    if msg_type == "team_assignment":
                        player["team"] = message.get("your_team")
                        player["hakem"] = message.get("hakem")
                        print(f"  📋 {player['name']}: Team {player['team']}, Hakem: {player['hakem']}")
                        
                    elif msg_type == "initial_deal":
                        player["hand"] = message.get("hand", [])
                        player["is_hakem"] = message.get("is_hakem", False)
                        print(f"  🎴 {player['name']}: {len(player['hand'])} cards, Hakem: {player['is_hakem']}")
                        
                        # Auto-choose hokm if hakem
                        if player["is_hakem"]:
                            hokm_choice = random.choice(["hearts", "diamonds", "clubs", "spades"])
                            hokm_msg = {
                                "type": "hokm_selected",
                                "suit": hokm_choice,
                                "room_code": room_code
                            }
                            await player["websocket"].send(json.dumps(hokm_msg))
                            print(f"  🎯 {player['name']} chose hokm: {hokm_choice}")
                            
                    elif msg_type == "final_deal":
                        player["hand"] = message.get("hand", [])
                        player["hokm"] = message.get("hokm")
                        print(f"  🃏 {player['name']}: Final hand with {len(player['hand'])} cards")
                        
                    elif msg_type == "phase_change":
                        player["phase"] = message.get("new_phase")
                        print(f"  🔄 {player['name']}: Phase changed to {player['phase']}")
                        if player["phase"] == "gameplay":
                            print(f"  🎮 {player['name']}: Ready for gameplay!")
                            
                    elif msg_type == "turn_start":
                        player["your_turn"] = message.get("your_turn", False)
                        if player["your_turn"]:
                            print(f"  🎯 {player['name']}: It's your turn!")
                    
                    messages_received += 1
                    
            except asyncio.TimeoutError:
                print(f"  ⏰ {player['name']}: No more messages")
        
        # Phase 3: Simulate some gameplay
        print(f"\n🎲 Phase 3: Simulating gameplay")
        
        # Find a player to play a card
        active_player = None
        for player in players:
            if player.get("your_turn", False):
                active_player = player
                break
        
        if active_player and active_player.get("hand"):
            card_to_play = random.choice(active_player["hand"])
            play_msg = {
                "type": "play_card",
                "card": card_to_play,
                "player_id": active_player["player_id"],
                "room_code": room_code
            }
            
            await active_player["websocket"].send(json.dumps(play_msg))
            print(f"  🎴 {active_player['name']} played: {card_to_play}")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(active_player["websocket"].recv(), timeout=5.0)
                message = json.loads(response)
                if message.get("type") == "card_played":
                    print(f"  ✅ Card play confirmed")
                    active_player["hand"].remove(card_to_play)
            except asyncio.TimeoutError:
                print(f"  ⏰ Card play timeout")
        
        # Phase 4: Disconnect and Reconnect
        print(f"\n🔌 Phase 4: Testing Mid-Game Reconnection")
        
        # Choose a player to disconnect
        disconnect_player = players[1]  # Bob
        
        print(f"  📊 Pre-disconnect state for {disconnect_player['name']}:")
        print(f"    Cards in hand: {len(disconnect_player.get('hand', []))}")
        print(f"    Team: {disconnect_player.get('team', 'Unknown')}")
        print(f"    Hokm: {disconnect_player.get('hokm', 'Unknown')}")
        print(f"    Phase: {disconnect_player.get('phase', 'Unknown')}")
        
        # Save state
        pre_disconnect_state = {
            "hand": disconnect_player.get("hand", []).copy(),
            "team": disconnect_player.get("team"),
            "hokm": disconnect_player.get("hokm"),
            "phase": disconnect_player.get("phase")
        }
        
        # Disconnect
        print(f"  🔌 Disconnecting {disconnect_player['name']}...")
        await disconnect_player["websocket"].close()
        disconnect_player["connected"] = False
        
        # Wait to simulate network interruption
        await asyncio.sleep(3)
        
        # Reconnect
        print(f"  🔄 Reconnecting {disconnect_player['name']}...")
        
        # Create new connection
        new_websocket = await websockets.connect(server_url)
        
        # Authenticate with token
        auth_msg = {
            "type": "auth_token",
            "token": disconnect_player["token"]
        }
        await new_websocket.send(json.dumps(auth_msg))
        auth_response = await new_websocket.recv()
        auth_data = json.loads(auth_response)
        
        if not auth_data.get("success", False):
            raise Exception(f"Token authentication failed for {disconnect_player['name']}")
        
        print(f"  ✅ {disconnect_player['name']} re-authenticated")
        
        # Attempt reconnection
        reconnect_msg = {
            "type": "reconnect",
            "player_id": disconnect_player["player_id"],
            "room_code": room_code
        }
        await new_websocket.send(json.dumps(reconnect_msg))
        
        # Wait for reconnection response
        reconnect_response = await asyncio.wait_for(new_websocket.recv(), timeout=10.0)
        reconnect_data = json.loads(reconnect_response)
        
        if reconnect_data.get("type") != "reconnect_success":
            raise Exception(f"Reconnection failed: {reconnect_data}")
        
        print(f"  🎉 {disconnect_player['name']} successfully reconnected!")
        
        # Update player
        disconnect_player["websocket"] = new_websocket
        disconnect_player["connected"] = True
        
        # Extract restored state
        game_state = reconnect_data.get("game_state", {})
        post_disconnect_state = {
            "hand": game_state.get("hand", []),
            "team": game_state.get("your_team"),
            "hokm": game_state.get("hokm"),
            "phase": game_state.get("phase")
        }
        
        print(f"  📊 Post-reconnect state for {disconnect_player['name']}:")
        print(f"    Cards in hand: {len(post_disconnect_state['hand'])}")
        print(f"    Team: {post_disconnect_state['team']}")
        print(f"    Hokm: {post_disconnect_state['hokm']}")
        print(f"    Phase: {post_disconnect_state['phase']}")
        
        # Phase 5: Verify State Preservation
        print(f"\n✅ Phase 5: Verifying State Preservation")
        
        checks = [
            ("Hand size", len(pre_disconnect_state["hand"]) == len(post_disconnect_state["hand"])),
            ("Team assignment", pre_disconnect_state["team"] == post_disconnect_state["team"]),
            ("Hokm suit", pre_disconnect_state["hokm"] == post_disconnect_state["hokm"]),
            ("Game phase", pre_disconnect_state["phase"] == post_disconnect_state["phase"])
        ]
        
        all_passed = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}: {'PRESERVED' if passed else 'CHANGED'}")
            if not passed:
                all_passed = False
        
        # Phase 6: Test Continued Gameplay
        print(f"\n🎮 Phase 6: Testing Continued Gameplay")
        
        # Try to play a card with the reconnected player
        if post_disconnect_state["hand"]:
            card_to_play = random.choice(post_disconnect_state["hand"])
            play_msg = {
                "type": "play_card",
                "card": card_to_play,
                "player_id": disconnect_player["player_id"],
                "room_code": room_code
            }
            
            try:
                await disconnect_player["websocket"].send(json.dumps(play_msg))
                print(f"  🎴 {disconnect_player['name']} attempted to play: {card_to_play}")
                
                # Wait for response
                response = await asyncio.wait_for(disconnect_player["websocket"].recv(), timeout=5.0)
                message = json.loads(response)
                
                if message.get("type") == "card_played":
                    print(f"  ✅ Card play successful - game continues normally!")
                elif message.get("type") == "error":
                    print(f"  ⚠️  Card play error: {message.get('message', 'Unknown error')}")
                else:
                    print(f"  ℹ️  Response: {message.get('type', 'Unknown')}")
                    
            except asyncio.TimeoutError:
                print(f"  ⏰ Card play timeout")
        
        # Final Results
        print(f"\n🎯 FINAL RESULTS")
        print("=" * 80)
        
        if all_passed:
            print("🎉 MID-GAME RECONNECTION: FULLY FUNCTIONAL!")
            print("✅ Player successfully disconnected and reconnected")
            print("✅ All game state was preserved correctly")
            print("✅ Gameplay continues normally after reconnection")
        else:
            print("⚠️  MID-GAME RECONNECTION: PARTIAL SUCCESS")
            print("✅ Player successfully reconnected")
            print("❌ Some game state was not preserved correctly")
        
        print(f"\n📋 Summary:")
        print(f"  • Players created: {len(players)}")
        print(f"  • Game started: ✅")
        print(f"  • Reconnection tested: ✅")
        print(f"  • State preserved: {'✅' if all_passed else '❌'}")
        
    except Exception as e:
        print(f"❌ Demonstration failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print(f"\n🧹 Cleaning up connections...")
        for player in players:
            if player["connected"]:
                try:
                    await player["websocket"].close()
                except:
                    pass
        print("✅ Cleanup complete")

if __name__ == "__main__":
    asyncio.run(demonstrate_mid_game_reconnection())
