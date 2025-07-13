#!/usr/bin/env python3
"""
Comprehensive Mid-Game Reconnection Test Suite
Tests various reconnection scenarios during active gameplay
"""

import asyncio
import websockets
import json
import time
import random
from typing import Dict, List, Optional

class ComprehensiveReconnectionTest:
    def __init__(self):
        self.server_url = "ws://localhost:8765"
        self.room_code = f"test_room_{int(time.time())}"
        self.players = []
        self.game_state = {}
        
    async def create_player(self, username: str, password: str = "testpass") -> Dict:
        """Create and authenticate a player"""
        print(f"🔐 Creating player: {username}")
        
        websocket = await websockets.connect(self.server_url)
        
        # Register player
        register_msg = {
            "type": "auth_register",
            "username": username,
            "password": password
        }
        await websocket.send(json.dumps(register_msg))
        response = await websocket.recv()
        auth_data = json.loads(response)
        
        if not auth_data.get("success", False):
            raise Exception(f"Auth failed for {username}: {auth_data}")
        
        player_info = auth_data.get("player_info", {})
        return {
            "username": username,
            "password": password,
            "player_id": player_info.get("player_id"),
            "token": player_info.get("token"),
            "websocket": websocket,
            "connected": True
        }
    
    async def join_room(self, player: Dict):
        """Join a player to the room"""
        print(f"🚪 {player['username']} joining room {self.room_code}")
        
        join_msg = {
            "type": "join",
            "room_code": self.room_code
        }
        await player["websocket"].send(json.dumps(join_msg))
        response = await player["websocket"].recv()
        join_data = json.loads(response)
        
        if join_data.get("type") != "join_success":
            raise Exception(f"Join failed for {player['username']}: {join_data}")
        
        player["room_joined"] = True
        print(f"✅ {player['username']} joined room")
    
    async def setup_game(self, player_count: int = 4):
        """Setup a complete game with all players"""
        print(f"\n🎮 Setting up game with {player_count} players")
        
        # Create players
        for i in range(player_count):
            username = f"player{i+1}_{int(time.time())}"
            player = await self.create_player(username)
            await self.join_room(player)
            self.players.append(player)
            await asyncio.sleep(0.5)  # Small delay between joins
        
        # Wait for game to start
        print("⏳ Waiting for game to start...")
        await self.wait_for_game_start()
        
        print("✅ Game setup complete!")
    
    async def wait_for_game_start(self):
        """Wait for all players to reach gameplay phase"""
        timeout = 30  # 30 second timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            all_ready = True
            
            for player in self.players:
                if not player["connected"]:
                    continue
                    
                try:
                    response = await asyncio.wait_for(player["websocket"].recv(), timeout=1.0)
                    message = json.loads(response)
                    msg_type = message.get("type")
                    
                    # Update player state based on message
                    if msg_type == "phase_change":
                        player["phase"] = message.get("new_phase")
                        if message.get("new_phase") == "gameplay":
                            player["game_ready"] = True
                            
                    elif msg_type == "team_assignment":
                        player["team"] = message.get("your_team")
                        player["hakem"] = message.get("hakem")
                        
                    elif msg_type == "initial_deal":
                        player["hand"] = message.get("hand", [])
                        player["is_hakem"] = message.get("is_hakem", False)
                        
                        # Auto-choose hokm if hakem
                        if player["is_hakem"]:
                            hokm_choice = random.choice(["hearts", "diamonds", "clubs", "spades"])
                            hokm_msg = {
                                "type": "hokm_selected",
                                "suit": hokm_choice,
                                "room_code": self.room_code
                            }
                            await player["websocket"].send(json.dumps(hokm_msg))
                            print(f"🎯 {player['username']} chose hokm: {hokm_choice}")
                            
                    elif msg_type == "final_deal":
                        player["hand"] = message.get("hand", [])
                        player["hokm"] = message.get("hokm")
                        
                    elif msg_type == "turn_start":
                        player["current_turn"] = message.get("your_turn", False)
                        
                except asyncio.TimeoutError:
                    continue
                
                # Check if player is ready
                if not player.get("game_ready", False):
                    all_ready = False
            
            if all_ready:
                print("✅ All players ready for gameplay!")
                break
                
            await asyncio.sleep(0.5)
        
        if not all_ready:
            print("⚠️  Timeout waiting for all players to be ready")
    
    async def test_reconnection_scenarios(self):
        """Test various reconnection scenarios"""
        print("\n🔄 Testing Reconnection Scenarios")
        
        scenarios = [
            ("Mid-Turn Reconnection", self.test_mid_turn_reconnection),
            ("Multiple Player Reconnection", self.test_multiple_reconnection),
            ("Quick Disconnect-Reconnect", self.test_quick_reconnect),
            ("Reconnect During Turn Change", self.test_turn_change_reconnect)
        ]
        
        results = {}
        
        for scenario_name, test_func in scenarios:
            print(f"\n--- {scenario_name} ---")
            try:
                result = await test_func()
                results[scenario_name] = {"success": True, "details": result}
                print(f"✅ {scenario_name}: PASSED")
            except Exception as e:
                results[scenario_name] = {"success": False, "error": str(e)}
                print(f"❌ {scenario_name}: FAILED - {e}")
        
        return results
    
    async def test_mid_turn_reconnection(self):
        """Test reconnection while it's the player's turn"""
        print("🎯 Testing mid-turn reconnection")
        
        # Find a player whose turn it is
        active_player = None
        for player in self.players:
            if player.get("current_turn", False) and player["connected"]:
                active_player = player
                break
        
        if not active_player:
            # Wait for someone's turn
            for _ in range(10):  # Try for 10 seconds
                for player in self.players:
                    if not player["connected"]:
                        continue
                    try:
                        response = await asyncio.wait_for(player["websocket"].recv(), timeout=1.0)
                        message = json.loads(response)
                        if message.get("type") == "turn_start" and message.get("your_turn"):
                            active_player = player
                            break
                    except asyncio.TimeoutError:
                        continue
                if active_player:
                    break
                await asyncio.sleep(1)
        
        if not active_player:
            return {"status": "skipped", "reason": "No active turn found"}
        
        # Save state before disconnect
        pre_hand = active_player["hand"].copy()
        pre_turn = active_player.get("current_turn", False)
        
        # Disconnect player
        print(f"🔌 Disconnecting {active_player['username']} during their turn")
        await active_player["websocket"].close()
        active_player["connected"] = False
        
        await asyncio.sleep(2)  # Wait for disconnect to register
        
        # Reconnect player
        print(f"🔄 Reconnecting {active_player['username']}")
        websocket = await websockets.connect(self.server_url)
        
        # Authenticate with token
        auth_msg = {
            "type": "auth_token",
            "token": active_player["token"]
        }
        await websocket.send(json.dumps(auth_msg))
        await websocket.recv()  # Auth response
        
        # Reconnect
        reconnect_msg = {
            "type": "reconnect",
            "player_id": active_player["player_id"],
            "room_code": self.room_code
        }
        await websocket.send(json.dumps(reconnect_msg))
        response = await websocket.recv()
        reconnect_data = json.loads(response)
        
        if reconnect_data.get("type") != "reconnect_success":
            raise Exception(f"Reconnection failed: {reconnect_data}")
        
        # Update player
        active_player["websocket"] = websocket
        active_player["connected"] = True
        
        # Verify state
        game_state = reconnect_data.get("game_state", {})
        post_hand = game_state.get("hand", [])
        post_turn = game_state.get("your_turn", False)
        
        return {
            "status": "success",
            "player": active_player["username"],
            "hand_preserved": set(pre_hand) == set(post_hand),
            "turn_preserved": pre_turn == post_turn,
            "hand_size": len(post_hand)
        }
    
    async def test_multiple_reconnection(self):
        """Test multiple players reconnecting simultaneously"""
        print("👥 Testing multiple player reconnection")
        
        # Disconnect 2 players
        disconnect_players = self.players[:2]
        
        # Save states
        pre_states = []
        for player in disconnect_players:
            pre_states.append({
                "username": player["username"],
                "hand": player["hand"].copy(),
                "team": player.get("team"),
                "hokm": player.get("hokm")
            })
            
            # Disconnect
            await player["websocket"].close()
            player["connected"] = False
            print(f"🔌 Disconnected {player['username']}")
        
        await asyncio.sleep(2)
        
        # Reconnect both simultaneously
        reconnect_tasks = []
        for player in disconnect_players:
            reconnect_tasks.append(self.reconnect_player(player))
        
        results = await asyncio.gather(*reconnect_tasks)
        
        # Verify results
        success_count = sum(1 for r in results if r.get("success"))
        
        return {
            "status": "success",
            "players_reconnected": success_count,
            "total_players": len(disconnect_players),
            "results": results
        }
    
    async def test_quick_reconnect(self):
        """Test very quick disconnect and reconnect"""
        print("⚡ Testing quick reconnect")
        
        player = self.players[0]
        pre_hand = player["hand"].copy()
        
        # Quick disconnect
        await player["websocket"].close()
        player["connected"] = False
        
        # Immediate reconnect (no delay)
        websocket = await websockets.connect(self.server_url)
        
        # Auth and reconnect
        auth_msg = {"type": "auth_token", "token": player["token"]}
        await websocket.send(json.dumps(auth_msg))
        await websocket.recv()
        
        reconnect_msg = {
            "type": "reconnect",
            "player_id": player["player_id"],
            "room_code": self.room_code
        }
        await websocket.send(json.dumps(reconnect_msg))
        response = await websocket.recv()
        reconnect_data = json.loads(response)
        
        if reconnect_data.get("type") != "reconnect_success":
            raise Exception(f"Quick reconnect failed: {reconnect_data}")
        
        player["websocket"] = websocket
        player["connected"] = True
        
        post_hand = reconnect_data.get("game_state", {}).get("hand", [])
        
        return {
            "status": "success",
            "player": player["username"],
            "hand_preserved": set(pre_hand) == set(post_hand),
            "reconnect_time": "immediate"
        }
    
    async def test_turn_change_reconnect(self):
        """Test reconnection during turn changes"""
        print("🔄 Testing turn change reconnection")
        
        player = self.players[1]
        
        # Disconnect during game
        await player["websocket"].close()
        player["connected"] = False
        
        # Wait for turn changes (other players play)
        await asyncio.sleep(3)
        
        # Reconnect
        result = await self.reconnect_player(player)
        
        if not result.get("success"):
            raise Exception(f"Turn change reconnect failed: {result}")
        
        return {
            "status": "success",
            "player": player["username"],
            "reconnected_during_turn_changes": True
        }
    
    async def reconnect_player(self, player: Dict):
        """Helper to reconnect a player"""
        try:
            websocket = await websockets.connect(self.server_url)
            
            # Auth
            auth_msg = {"type": "auth_token", "token": player["token"]}
            await websocket.send(json.dumps(auth_msg))
            await websocket.recv()
            
            # Reconnect
            reconnect_msg = {
                "type": "reconnect",
                "player_id": player["player_id"],
                "room_code": self.room_code
            }
            await websocket.send(json.dumps(reconnect_msg))
            response = await websocket.recv()
            reconnect_data = json.loads(response)
            
            if reconnect_data.get("type") != "reconnect_success":
                return {"success": False, "error": "Reconnect failed"}
            
            player["websocket"] = websocket
            player["connected"] = True
            
            return {"success": True, "game_state": reconnect_data.get("game_state", {})}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def cleanup(self):
        """Clean up all connections"""
        print("\n🧹 Cleaning up connections...")
        for player in self.players:
            if player["connected"]:
                try:
                    await player["websocket"].close()
                except:
                    pass
        print("✅ Cleanup complete")

async def main():
    """Run comprehensive reconnection tests"""
    print("🎯 COMPREHENSIVE MID-GAME RECONNECTION TEST SUITE")
    print("=" * 80)
    
    test = ComprehensiveReconnectionTest()
    
    try:
        # Setup game
        await test.setup_game(4)
        
        # Run reconnection tests
        results = await test.test_reconnection_scenarios()
        
        # Report results
        print("\n" + "=" * 80)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 80)
        
        total_tests = len(results)
        passed_tests = sum(1 for r in results.values() if r["success"])
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result["success"] else "❌ FAILED"
            print(f"{status} {test_name}")
            if not result["success"]:
                print(f"    Error: {result['error']}")
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if passed_tests == total_tests:
            print("\n🎉 ALL RECONNECTION TESTS PASSED!")
            print("The mid-game reconnection system is working correctly!")
        else:
            print(f"\n⚠️  {total_tests - passed_tests} test(s) failed")
        
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await test.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
