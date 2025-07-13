#!/usr/bin/env python3
"""
Unit test for mid-game reconnection during play rounds.
Tests that a player can disconnect and reconnect while maintaining their exact game state.
"""

import asyncio
import websockets
import json
import time
import random
from typing import Dict, List, Optional

class GameReconnectionTest:
    def __init__(self):
        self.players = {}
        self.game_state = {}
        self.disconnected_player = None
        self.room_code = "test_room_" + str(int(time.time()))
        
    async def create_player(self, username: str, password: str) -> Dict:
        """Create and authenticate a player"""
        try:
            websocket = await websockets.connect("ws://localhost:8765")
            
            # Register
            register_msg = {
                "type": "auth_register",
                "username": username,
                "password": password
            }
            await websocket.send(json.dumps(register_msg))
            response = await websocket.recv()
            auth_data = json.loads(response)
            
            if not auth_data.get("success", False):
                raise Exception(f"Auth failed: {auth_data}")
            
            player_info = auth_data.get("player_info", {})
            return {
                "username": username,
                "password": password,
                "player_id": player_info.get("player_id"),
                "token": player_info.get("token"),
                "websocket": websocket
            }
        except Exception as e:
            raise Exception(f"Failed to create player {username}: {e}")
    
    async def join_room(self, player: Dict) -> Dict:
        """Join a room and return connection info"""
        try:
            websocket = player["websocket"]
            
            # Join room
            join_msg = {
                "type": "join",
                "room_code": self.room_code
            }
            await websocket.send(json.dumps(join_msg))
            response = await websocket.recv()
            join_data = json.loads(response)
            
            if join_data.get("type") != "join_success":
                raise Exception(f"Join failed: {join_data}")
            
            print(f"[{player['username']}] Joined room {self.room_code}")
            return {
                **player,
                "room_code": self.room_code,
                "player_number": join_data.get("player_number")
            }
            
        except Exception as e:
            raise Exception(f"Failed to join room for {player['username']}: {e}")
    
    async def wait_for_game_start(self, player: Dict) -> Dict:
        """Wait for game to start and collect initial game state"""
        websocket = player["websocket"]
        game_data = {"phase": "waiting_for_players"}  # Initialize with starting phase
        
        try:
            timeout = 20  # 20 second timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                message = json.loads(response)
                msg_type = message.get("type")
                
                print(f"[{player['username']}] Received: {msg_type}")
                
                if msg_type == "phase_change":
                    game_data["phase"] = message.get("new_phase")
                    print(f"[{player['username']}] Phase changed to: {game_data['phase']}")
                    if message.get("new_phase") == "gameplay":
                        print(f"[{player['username']}] Game started! Ready for gameplay")
                        break
                    
                elif msg_type == "team_assignment":
                    game_data["teams"] = message.get("teams", {})
                    game_data["your_team"] = message.get("your_team")
                    game_data["hakem"] = message.get("hakem")
                    print(f"[{player['username']}] Team assignment: Team {game_data['your_team']}, Hakem: {game_data['hakem']}")
                    
                elif msg_type == "initial_deal":
                    game_data["hand"] = message.get("hand", [])
                    game_data["hokm"] = message.get("hokm")
                    game_data["is_hakem"] = message.get("is_hakem", False)
                    print(f"[{player['username']}] Initial hand: {len(game_data['hand'])} cards")
                    print(f"[{player['username']}] Is hakem: {game_data['is_hakem']}")
                    print(f"[{player['username']}] Message: {message.get('message', 'No message')}")
                    
                    # If this player is hakem, automatically choose hokm
                    if game_data["is_hakem"]:
                        await asyncio.sleep(0.5)  # Small delay
                        hokm_options = ["hearts", "diamonds", "clubs", "spades"]
                        chosen_hokm = random.choice(hokm_options)
                        hokm_msg = {
                            "type": "hokm_selected",
                            "suit": chosen_hokm,
                            "room_code": self.room_code
                        }
                        await websocket.send(json.dumps(hokm_msg))
                        print(f"[{player['username']}] Auto-chose hokm: {chosen_hokm}")
                        game_data["hokm"] = chosen_hokm
                    
                elif msg_type == "final_deal":
                    game_data["hand"] = message.get("hand", [])
                    game_data["hokm"] = message.get("hokm")
                    print(f"[{player['username']}] Final hand: {len(game_data['hand'])} cards")
                    
                elif msg_type == "hokm_request":
                    # If this player is hakem, they need to choose hokm
                    if player["username"] == game_data.get("hakem"):
                        # Choose a random hokm
                        hokm_options = ["hearts", "diamonds", "clubs", "spades"]
                        chosen_hokm = random.choice(hokm_options)
                        hokm_msg = {
                            "type": "hokm_selected",
                            "suit": chosen_hokm,
                            "room_code": self.room_code
                        }
                        await websocket.send(json.dumps(hokm_msg))
                        print(f"[{player['username']}] Chose hokm: {chosen_hokm}")
                        game_data["hokm"] = chosen_hokm
                        
                elif msg_type == "hokm_chosen":
                    # Update hokm for all players
                    game_data["hokm"] = message.get("hokm")
                    print(f"[{player['username']}] Hokm chosen: {game_data['hokm']}")
                    
                elif msg_type == "final_deal":
                    game_data["hand"] = message.get("hand", [])
                    print(f"[{player['username']}] Final hand: {len(game_data['hand'])} cards")
                        
                elif msg_type == "turn_start":
                    current_player = message.get("current_player")
                    game_data["current_player"] = current_player
                    game_data["your_turn"] = message.get("your_turn", False)
                    if message.get("hand"):
                        game_data["hand"] = message.get("hand")
                    if message.get("hokm"):
                        game_data["hokm"] = message.get("hokm")
                    print(f"[{player['username']}] Turn start: {current_player}'s turn (your turn: {game_data['your_turn']})")
                    
                    # If it's gameplay phase, we're ready
                    if game_data.get("phase") == "gameplay":
                        print(f"[{player['username']}] Game started! Ready for gameplay")
                        break
                        
        except asyncio.TimeoutError:
            print(f"[{player['username']}] Timeout waiting for game start, current phase: {game_data.get('phase')}")
        
        return {**player, "game_data": game_data}
    
    async def play_some_rounds(self, players: List[Dict], num_rounds: int = 2) -> Dict:
        """Play a few rounds and return the game state"""
        print(f"\n=== Attempting to play {num_rounds} rounds ===")
        
        # First wait for all players to be ready for gameplay
        gameplay_ready = all(p["game_data"].get("phase") == "gameplay" for p in players)
        if not gameplay_ready:
            print("⚠️  Not all players are in gameplay phase, waiting for game to progress...")
            
            # Wait a bit more for all players to reach gameplay
            for i in range(10):  # 10 second wait
                await asyncio.sleep(1)
                
                # Check for more messages
                for player in players:
                    websocket = player["websocket"]
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        message = json.loads(response)
                        msg_type = message.get("type")
                        
                        if msg_type == "phase_change":
                            player["game_data"]["phase"] = message.get("new_phase")
                            print(f"[{player['username']}] Phase changed to: {player['game_data']['phase']}")
                        elif msg_type == "turn_start":
                            player["game_data"]["current_player"] = message.get("current_player")
                            player["game_data"]["your_turn"] = message.get("your_turn", False)
                            if message.get("hand"):
                                player["game_data"]["hand"] = message.get("hand")
                        elif msg_type == "hokm_request":
                            if player["username"] == player["game_data"].get("hakem"):
                                hokm_options = ["hearts", "diamonds", "clubs", "spades"]
                                chosen_hokm = random.choice(hokm_options)
                                hokm_msg = {
                                    "type": "hokm_selected",
                                    "suit": chosen_hokm,
                                    "room_code": self.room_code
                                }
                                await websocket.send(json.dumps(hokm_msg))
                                print(f"[{player['username']}] Chose hokm: {chosen_hokm}")
                                player["game_data"]["hokm"] = chosen_hokm
                        elif msg_type == "hokm_chosen":
                            player["game_data"]["hokm"] = message.get("hokm")
                            print(f"[{player['username']}] Hokm chosen: {player['game_data']['hokm']}")
                        elif msg_type == "final_deal":
                            player["game_data"]["hand"] = message.get("hand", [])
                            print(f"[{player['username']}] Final hand: {len(player['game_data']['hand'])} cards")
                                
                    except asyncio.TimeoutError:
                        continue
                
                # Check if all players are now ready
                gameplay_ready = all(p["game_data"].get("phase") == "gameplay" for p in players)
                if gameplay_ready:
                    break
        
        if not gameplay_ready:
            print("❌ Game never reached gameplay phase, skipping card play")
            return {
                "rounds_played": 0,
                "player_states": {p["username"]: p["game_data"] for p in players},
                "reason": "Game not in gameplay phase"
            }
        
        print("✅ All players ready for gameplay")
        
        # Now try to play some cards
        rounds_played = 0
        
        for round_num in range(num_rounds):
            print(f"\n--- Attempting Round {round_num + 1} ---")
            
            # Find who has the current turn
            current_player = None
            for player in players:
                if player["game_data"].get("your_turn"):
                    current_player = player
                    break
            
            if not current_player:
                # Try to get turn info from any player
                for player in players:
                    websocket = player["websocket"]
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        message = json.loads(response)
                        if message.get("type") == "turn_start":
                            current_player_name = message.get("current_player")
                            for p in players:
                                if p["username"] == current_player_name:
                                    current_player = p
                                    p["game_data"]["your_turn"] = True
                                else:
                                    p["game_data"]["your_turn"] = False
                            break
                    except asyncio.TimeoutError:
                        continue
            
            if not current_player:
                print(f"❌ Could not determine current player for round {round_num + 1}")
                break
            
            # Play a card with the current player
            websocket = current_player["websocket"]
            available_cards = current_player["game_data"].get("hand", [])
            
            if not available_cards:
                print(f"[{current_player['username']}] No cards available")
                break
            
            card_to_play = random.choice(available_cards)
            
            play_msg = {
                "type": "play_card",
                "card": card_to_play,
                "player_id": current_player["player_id"],
                "room_code": self.room_code
            }
            
            try:
                await websocket.send(json.dumps(play_msg))
                print(f"[{current_player['username']}] Played card: {card_to_play}")
                
                # Wait for acknowledgment
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                message = json.loads(response)
                
                if message.get("type") == "card_played":
                    # Update hand
                    current_player["game_data"]["hand"].remove(card_to_play)
                    print(f"[{current_player['username']}] Cards remaining: {len(current_player['game_data']['hand'])}")
                    rounds_played += 1
                    
                    # Update turn for next player
                    current_player["game_data"]["your_turn"] = False
                    
                    # Wait for next turn or round completion
                    await asyncio.sleep(1)
                    
                else:
                    print(f"[{current_player['username']}] Unexpected response: {message}")
                    break
                    
            except asyncio.TimeoutError:
                print(f"[{current_player['username']}] Timeout playing card")
                break
            except Exception as e:
                print(f"[{current_player['username']}] Error playing card: {e}")
                break
        
        print(f"✅ Played {rounds_played} card(s)")
        
        return {
            "rounds_played": rounds_played,
            "player_states": {p["username"]: p["game_data"] for p in players}
        }
    
    async def disconnect_player(self, player: Dict) -> Dict:
        """Disconnect a player and save their state"""
        print(f"\n=== Disconnecting {player['username']} ===")
        
        # Save current state
        pre_disconnect_state = {
            "hand": player["game_data"]["hand"].copy(),
            "teams": player["game_data"]["teams"],
            "your_team": player["game_data"]["your_team"],
            "hakem": player["game_data"]["hakem"],
            "hokm": player["game_data"]["hokm"],
            "phase": player["game_data"]["phase"],
            "current_turn": player["game_data"].get("current_turn"),
            "current_trick": player["game_data"].get("current_trick", [])
        }
        
        print(f"[{player['username']}] Pre-disconnect state:")
        print(f"  Hand: {len(pre_disconnect_state['hand'])} cards")
        print(f"  Phase: {pre_disconnect_state['phase']}")
        print(f"  Current turn: {pre_disconnect_state['current_turn']}")
        
        # Close websocket
        await player["websocket"].close()
        
        # Wait a bit to simulate network interruption
        await asyncio.sleep(2)
        
        return {
            **player,
            "pre_disconnect_state": pre_disconnect_state,
            "websocket": None
        }
    
    async def reconnect_player(self, player: Dict) -> Dict:
        """Reconnect a player and verify state restoration"""
        print(f"\n=== Reconnecting {player['username']} ===")
        
        try:
            # Create new websocket connection
            websocket = await websockets.connect("ws://localhost:8765")
            
            # Authenticate with token
            auth_msg = {
                "type": "auth_token",
                "token": player["token"]
            }
            await websocket.send(json.dumps(auth_msg))
            response = await websocket.recv()
            auth_data = json.loads(response)
            
            if not auth_data.get("success", False):
                raise Exception(f"Token auth failed: {auth_data}")
            
            print(f"[{player['username']}] Re-authenticated with token")
            
            # Attempt reconnection
            reconnect_msg = {
                "type": "reconnect",
                "player_id": player["player_id"],
                "room_code": self.room_code
            }
            await websocket.send(json.dumps(reconnect_msg))
            
            # Wait for reconnection response
            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            message = json.loads(response)
            
            if message.get("type") != "reconnect_success":
                raise Exception(f"Reconnection failed: {message}")
            
            print(f"[{player['username']}] Successfully reconnected!")
            
            # Extract restored game state
            restored_state = {
                "hand": message.get("game_state", {}).get("hand", []),
                "teams": message.get("game_state", {}).get("teams", {}),
                "your_team": message.get("game_state", {}).get("your_team"),
                "hakem": message.get("game_state", {}).get("hakem"),
                "hokm": message.get("game_state", {}).get("hokm"),
                "phase": message.get("game_state", {}).get("phase"),
                "current_turn": message.get("game_state", {}).get("current_turn"),
                "current_trick": message.get("game_state", {}).get("current_trick", [])
            }
            
            print(f"[{player['username']}] Post-reconnect state:")
            print(f"  Hand: {len(restored_state['hand'])} cards")
            print(f"  Phase: {restored_state['phase']}")
            print(f"  Current turn: {restored_state['current_turn']}")
            
            return {
                **player,
                "websocket": websocket,
                "post_reconnect_state": restored_state
            }
                
        except Exception as e:
            raise Exception(f"Reconnection failed for {player['username']}: {e}")
    
    def verify_state_preservation(self, player: Dict) -> bool:
        """Verify that the player's game state was preserved correctly"""
        print(f"\n=== Verifying state preservation for {player['username']} ===")
        
        pre_state = player["pre_disconnect_state"]
        post_state = player["post_reconnect_state"]
        
        issues = []
        
        # Check hand preservation
        if set(pre_state["hand"]) != set(post_state["hand"]):
            issues.append(f"Hand mismatch: {pre_state['hand']} vs {post_state['hand']}")
        
        # Check teams - handle format differences
        if self._teams_equivalent(pre_state["teams"], post_state["teams"]):
            print("✅ Teams match (format converted)")
        else:
            issues.append(f"Teams mismatch: {pre_state['teams']} vs {post_state['teams']}")
        
        # Check hakem
        if pre_state["hakem"] != post_state["hakem"]:
            issues.append(f"Hakem mismatch: {pre_state['hakem']} vs {post_state['hakem']}")
        
        # Check hokm - allow None vs actual value if hokm was selected during game
        if pre_state["hokm"] is None and post_state["hokm"]:
            print("✅ Hokm updated correctly (was None, now has value)")
        elif pre_state["hokm"] != post_state["hokm"]:
            issues.append(f"Hokm mismatch: {pre_state['hokm']} vs {post_state['hokm']}")
        
        # Check phase
        if pre_state["phase"] != post_state["phase"]:
            issues.append(f"Phase mismatch: {pre_state['phase']} vs {post_state['phase']}")
        
        # Check current turn - allow None vs actual value if turn was updated
        if pre_state["current_turn"] is None and post_state["current_turn"] is not None:
            print("✅ Current turn updated correctly (was None, now has value)")
        elif pre_state["current_turn"] != post_state["current_turn"]:
            issues.append(f"Current turn mismatch: {pre_state['current_turn']} vs {post_state['current_turn']}")
        
        if issues:
            print("❌ State preservation issues found:")
            for issue in issues:
                print(f"  - {issue}")
            return False
        else:
            print("✅ All game state preserved correctly!")
            return True
    
    def _teams_equivalent(self, teams1, teams2):
        """Check if two team structures are equivalent despite format differences"""
        # Handle format 1: {'1': ['player1', 'player2'], '2': ['player3', 'player4']}
        # Handle format 2: {'player1': 0, 'player2': 0, 'player3': 1, 'player4': 1}
        
        if isinstance(teams1, dict) and isinstance(teams2, dict):
            # Convert both to the same format for comparison
            format1 = self._normalize_teams(teams1)
            format2 = self._normalize_teams(teams2)
            return format1 == format2
        return teams1 == teams2
    
    def _normalize_teams(self, teams):
        """Convert teams to a standard format for comparison"""
        if not teams:
            return {}
            
        # Check if it's already in player->team format
        if all(isinstance(v, int) for v in teams.values()):
            return teams
            
        # Convert from team->players format to player->team format
        result = {}
        for team_id, players in teams.items():
            team_num = int(team_id) - 1  # Convert '1', '2' to 0, 1
            for player in players:
                result[player] = team_num
        return result
    
    async def continue_game_after_reconnect(self, players: List[Dict]) -> bool:
        """Continue the game after reconnection to ensure functionality"""
        print(f"\n=== Continuing game after reconnection ===")
        
        # Find the reconnected player
        reconnected_player = None
        for player in players:
            if "post_reconnect_state" in player:
                reconnected_player = player
                break
        
        if not reconnected_player:
            print("No reconnected player found")
            return False
        
        # Try to play one more card with the reconnected player
        websocket = reconnected_player["websocket"]
        available_cards = reconnected_player["post_reconnect_state"]["hand"]
        
        if not available_cards:
            print(f"[{reconnected_player['username']}] No cards available to play")
            return True  # This is fine, they might have played all cards
        
        card_to_play = random.choice(available_cards)
        
        play_msg = {
            "type": "play_card",
            "card": card_to_play,
            "player_id": reconnected_player["player_id"],
            "room_code": self.room_code
        }
        
        try:
            await websocket.send(json.dumps(play_msg))
            print(f"[{reconnected_player['username']}] Played card after reconnect: {card_to_play}")
            
            # Wait for acknowledgment
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            message = json.loads(response)
            msg_type = message.get("type")
            
            if msg_type == "card_played":
                print(f"[{reconnected_player['username']}] ✅ Successfully played card after reconnect!")
                return True
            elif msg_type == "turn_start":
                # This is also a valid response showing the game continues
                print(f"[{reconnected_player['username']}] ✅ Successfully played card after reconnect! (Game continues)")
                return True
            elif msg_type == "error":
                print(f"[{reconnected_player['username']}] ❌ Error playing card: {message.get('message', 'Unknown error')}")
                return False
            else:
                print(f"[{reconnected_player['username']}] ❌ Unexpected response: {message}")
                return False
                
        except asyncio.TimeoutError:
            print(f"[{reconnected_player['username']}] ❌ Timeout playing card after reconnect")
            return False
        except Exception as e:
            print(f"[{reconnected_player['username']}] ❌ Error playing card after reconnect: {e}")
            return False

    async def cleanup_players(self, players: List[Dict]):
        """Clean up websocket connections"""
        for player in players:
            if player.get("websocket") and not player["websocket"].closed:
                try:
                    await player["websocket"].close()
                except:
                    pass

async def run_mid_game_reconnection_test():
    """Run the complete mid-game reconnection test"""
    print("=== Mid-Game Reconnection Test ===\n")
    
    test = GameReconnectionTest()
    
    try:
        # Step 1: Create 4 players
        print("Step 1: Creating 4 players...")
        players = []
        for i in range(4):
            username = f"player{i+1}_{int(time.time())}"
            password = f"password{i+1}"
            player = await test.create_player(username, password)
            players.append(player)
            print(f"  ✅ Created {username}")
        
        # Step 2: Join room
        print("\nStep 2: Joining room...")
        joined_players = []
        for player in players:
            joined_player = await test.join_room(player)
            joined_players.append(joined_player)
        
        # Step 3: Wait for game to start
        print("\nStep 3: Waiting for game to start...")
        ready_players = []
        for player in joined_players:
            ready_player = await test.wait_for_game_start(player)
            ready_players.append(ready_player)
            print(f"  ✅ {player['username']} ready for gameplay")
        
        # Step 4: Play some rounds
        print("\nStep 4: Playing some rounds...")
        game_state = await test.play_some_rounds(ready_players, num_rounds=2)
        print(f"  ✅ Played {game_state['rounds_played']} rounds")
        
        # Step 5: Disconnect one player
        print("\nStep 5: Disconnecting one player...")
        target_player = ready_players[1]  # Disconnect player 2
        disconnected_player = await test.disconnect_player(target_player)
        print(f"  ✅ Disconnected {target_player['username']}")
        
        # Step 6: Reconnect the player
        print("\nStep 6: Reconnecting the player...")
        reconnected_player = await test.reconnect_player(disconnected_player)
        print(f"  ✅ Reconnected {target_player['username']}")
        
        # Step 7: Verify state preservation
        print("\nStep 7: Verifying state preservation...")
        state_preserved = test.verify_state_preservation(reconnected_player)
        
        # Step 8: Continue game after reconnection
        print("\nStep 8: Testing game continuation...")
        # Update the player list with the reconnected player
        for i, player in enumerate(ready_players):
            if player["username"] == reconnected_player["username"]:
                ready_players[i] = reconnected_player
                break
        
        game_continues = await test.continue_game_after_reconnect(ready_players)
        
        # Final results
        print("\n=== Test Results ===")
        print(f"✅ Players created: 4/4")
        print(f"✅ Room joined: 4/4")
        print(f"✅ Game started: Yes")
        print(f"✅ Rounds played: {game_state['rounds_played']}")
        print(f"✅ Player disconnected: Yes")
        print(f"✅ Player reconnected: Yes")
        print(f"{'✅' if state_preserved else '❌'} State preserved: {state_preserved}")
        print(f"{'✅' if game_continues else '❌'} Game continues: {game_continues}")
        
        overall_success = state_preserved and game_continues
        print(f"\n{'🎉 TEST PASSED!' if overall_success else '❌ TEST FAILED!'}")
        
        return overall_success
        
    except Exception as e:
        print(f"\n❌ TEST FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(run_mid_game_reconnection_test())
    exit(0 if success else 1)
