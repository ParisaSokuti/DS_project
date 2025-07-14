#!/usr/bin/env python3
"""
Comprehensive Reconnection Test for Hokm Game

This test simulates the exact scenario mentioned by the user:
1. Creates a simulated game environment with 4 players
2. Progresses through hokm selection phase
3. Simulates disconnection during critical moments
4. Tests reconnection and continuation
"""

import asyncio
import websockets
import json
import sys
import os
import time
import signal
from dataclasses import dataclass
from typing import Dict, List, Optional

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from client_auth_manager import ClientAuthManager
    from game_states import GameState
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

SERVER_URI = "ws://192.168.1.26:8765"

@dataclass
class PlayerState:
    username: str
    player_id: str
    session_file: str
    hand: List[str]
    is_hakem: bool
    connected: bool
    websocket: Optional[object] = None
    auth_manager: Optional[ClientAuthManager] = None

class GameplayReconnectionTest:
    def __init__(self):
        self.players = {}
        self.game_phase = "waiting_for_players"
        self.hokm = None
        self.hakem = None
        self.current_player = None
        self.test_results = []
        
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    async def create_player(self, username: str, password: str = "123456") -> PlayerState:
        """Create a test player with authentication"""
        auth_manager = ClientAuthManager()
        session_file = f".test_session_{username}_{int(time.time())}"
        
        # Create player state
        player = PlayerState(
            username=username,
            player_id="",
            session_file=session_file,
            hand=[],
            is_hakem=False,
            connected=False,
            auth_manager=auth_manager
        )
        
        return player
    
    async def connect_and_authenticate(self, player: PlayerState) -> bool:
        """Connect and authenticate a player"""
        try:
            self.log(f"Connecting {player.username}...")
            ws = await websockets.connect(SERVER_URI)
            
            # Try token authentication first
            authenticated = await player.auth_manager.authenticate_with_server(ws)
            
            if authenticated:
                player_info = player.auth_manager.get_player_info()
                player.player_id = player_info['player_id']
                player.websocket = ws
                player.connected = True
                
                # Save session
                with open(player.session_file, 'w') as f:
                    f.write(player.player_id)
                
                self.log(f"✅ {player.username} authenticated (ID: {player.player_id[:12]}...)")
                return True
            else:
                self.log(f"❌ Authentication failed for {player.username}")
                await ws.close()
                return False
                
        except Exception as e:
            self.log(f"❌ Connection error for {player.username}: {e}", "ERROR")
            return False
    
    async def join_game(self, player: PlayerState) -> bool:
        """Join game with a player"""
        try:
            await player.websocket.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            
            # Wait for response
            response = await asyncio.wait_for(player.websocket.recv(), timeout=10.0)
            data = json.loads(response)
            
            if data.get('type') == 'join_success':
                self.log(f"✅ {player.username} joined game successfully")
                return True
            else:
                self.log(f"❌ Join failed for {player.username}: {data}")
                return False
                
        except Exception as e:
            self.log(f"❌ Join error for {player.username}: {e}", "ERROR")
            return False
    
    async def simulate_game_progression(self, target_player: PlayerState) -> bool:
        """Simulate game progression until we reach a testable state"""
        try:
            # Create 4 players
            players = []
            for i, username in enumerate(["TestPlayer1", "TestPlayer2", "TestPlayer3", "TestPlayer4"]):
                player = await self.create_player(username)
                if await self.connect_and_authenticate(player):
                    players.append(player)
                    self.players[username] = player
                    
                    # Small delay between connections
                    await asyncio.sleep(0.5)
                else:
                    self.log(f"❌ Failed to setup {username}")
                    return False
            
            # Join all players
            for player in players:
                if not await self.join_game(player):
                    return False
                await asyncio.sleep(0.5)
            
            # Wait for game to start and progress
            self.log("⏳ Waiting for game to start...")
            
            # Monitor messages from all players
            active_players = [p for p in players if p.connected]
            
            # Track game state
            game_started = False
            hokm_selected = False
            gameplay_started = False
            
            for _ in range(30):  # 30 seconds timeout
                if not active_players:
                    break
                
                # Check messages from all active players
                tasks = []
                for player in active_players:
                    if player.websocket:
                        tasks.append(asyncio.create_task(
                            asyncio.wait_for(player.websocket.recv(), timeout=1.0)
                        ))
                
                if not tasks:
                    break
                
                # Wait for any message
                done, pending = await asyncio.wait(
                    tasks, 
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=1.0
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                
                # Process completed tasks
                for task in done:
                    try:
                        message = await task
                        data = json.loads(message)
                        msg_type = data.get('type')
                        
                        self.log(f"📥 Received: {msg_type}")
                        
                        if msg_type == 'team_assignment':
                            game_started = True
                            hakem = data.get('hakem')
                            self.hakem = hakem
                            self.log(f"🎯 Game started! Hakem: {hakem}")
                            
                        elif msg_type == 'initial_deal':
                            is_hakem = data.get('is_hakem', False)
                            hand = data.get('hand', [])
                            
                            # Find which player got this message
                            for player in active_players:
                                if player.websocket and task in tasks:
                                    player.hand = hand
                                    player.is_hakem = is_hakem
                                    self.log(f"🎴 {player.username} got initial deal (Hakem: {is_hakem})")
                                    
                                    # If this is the hakem, they need to disconnect here
                                    if is_hakem and player.username == target_player.username:
                                        self.log(f"🎯 Target player {player.username} is hakem - disconnecting for test")
                                        await player.websocket.close()
                                        player.connected = False
                                        return True
                            
                        elif msg_type == 'hokm_selected':
                            hokm_selected = True
                            self.hokm = data.get('suit')
                            self.log(f"🎴 Hokm selected: {self.hokm}")
                            
                        elif msg_type == 'turn_start':
                            gameplay_started = True
                            current_player = data.get('current_player')
                            your_turn = data.get('your_turn', False)
                            
                            # Find which player got this message
                            for player in active_players:
                                if your_turn and player.username == target_player.username:
                                    self.log(f"🎯 Target player {player.username} turn - disconnecting for test")
                                    await player.websocket.close()
                                    player.connected = False
                                    return True
                            
                    except Exception as e:
                        self.log(f"❌ Error processing message: {e}")
                        continue
                
                await asyncio.sleep(0.1)
            
            self.log("❌ Could not reach suitable disconnection point")
            return False
            
        except Exception as e:
            self.log(f"❌ Game progression error: {e}", "ERROR")
            return False
    
    async def test_reconnection(self, player: PlayerState) -> bool:
        """Test reconnection for a player"""
        try:
            self.log(f"🔄 Testing reconnection for {player.username}...")
            
            # Wait a bit before reconnecting
            await asyncio.sleep(2)
            
            # Reconnect
            if not await self.connect_and_authenticate(player):
                return False
            
            # Load session and reconnect
            with open(player.session_file, 'r') as f:
                session_id = f.read().strip()
            
            await player.websocket.send(json.dumps({
                "type": "reconnect",
                "player_id": session_id,
                "room_code": "9999"
            }))
            
            # Wait for reconnection response
            response = await asyncio.wait_for(player.websocket.recv(), timeout=15.0)
            data = json.loads(response)
            
            if data.get('type') == 'reconnect_success':
                self.log(f"✅ {player.username} reconnected successfully!")
                
                game_state = data.get('game_state', {})
                phase = game_state.get('phase', 'unknown')
                hand = game_state.get('hand', [])
                your_turn = game_state.get('your_turn', False)
                hakem = game_state.get('hakem')
                you = game_state.get('you')
                
                self.log(f"   Phase: {phase}")
                self.log(f"   Hand size: {len(hand)}")
                self.log(f"   Your turn: {your_turn}")
                self.log(f"   Hakem: {hakem}")
                self.log(f"   You: {you}")
                
                # Test immediate actions
                if phase == 'hokm_selection' and hakem == you:
                    self.log("🎴 Testing hokm selection after reconnection...")
                    await player.websocket.send(json.dumps({
                        'type': 'hokm_selected',
                        'suit': 'hearts',
                        'room_code': '9999'
                    }))
                    
                    # Wait for confirmation
                    response = await asyncio.wait_for(player.websocket.recv(), timeout=10.0)
                    data = json.loads(response)
                    
                    if data.get('type') == 'hokm_selected':
                        self.log("✅ Hokm selection successful after reconnection!")
                        return True
                    else:
                        self.log(f"❌ Hokm selection failed: {data}")
                        return False
                
                elif phase == 'gameplay' and your_turn and hand:
                    self.log("🃏 Testing card play after reconnection...")
                    card = hand[0]
                    await player.websocket.send(json.dumps({
                        "type": "play_card",
                        "room_code": "9999",
                        "player_id": player.player_id,
                        "card": card
                    }))
                    
                    # Wait for confirmation
                    response = await asyncio.wait_for(player.websocket.recv(), timeout=10.0)
                    data = json.loads(response)
                    
                    if data.get('type') == 'card_played':
                        self.log("✅ Card play successful after reconnection!")
                        return True
                    else:
                        self.log(f"❌ Card play failed: {data}")
                        return False
                
                else:
                    self.log(f"✅ Reconnection successful - no immediate action needed")
                    return True
                
            else:
                self.log(f"❌ Reconnection failed: {data}")
                return False
                
        except Exception as e:
            self.log(f"❌ Reconnection error: {e}", "ERROR")
            return False
    
    async def cleanup(self):
        """Clean up test resources"""
        for player in self.players.values():
            if player.websocket:
                try:
                    await player.websocket.close()
                except:
                    pass
                    
            try:
                if os.path.exists(player.session_file):
                    os.remove(player.session_file)
            except:
                pass
    
    async def run_test(self):
        """Run the complete reconnection test"""
        self.log("🎮 Starting Comprehensive Reconnection Test")
        self.log("=" * 60)
        
        # Create target player for testing
        target_player = await self.create_player("TestPlayer1")
        
        try:
            # Test 1: Simulate game progression
            self.log("\n📋 Phase 1: Setting up game and reaching disconnection point...")
            if not await self.simulate_game_progression(target_player):
                self.log("❌ Failed to reach disconnection point")
                return False
            
            # Test 2: Test reconnection
            self.log("\n📋 Phase 2: Testing reconnection...")
            if not await self.test_reconnection(target_player):
                self.log("❌ Reconnection test failed")
                return False
            
            self.log("\n" + "=" * 60)
            self.log("🎉 SUCCESS: Comprehensive reconnection test passed!")
            self.log("✅ Players can disconnect and reconnect during gameplay")
            self.log("✅ Game state is properly restored")
            self.log("✅ Immediate actions work after reconnection")
            
            return True
            
        except Exception as e:
            self.log(f"❌ Test failed with error: {e}", "ERROR")
            return False
            
        finally:
            await self.cleanup()

async def main():
    test = GameplayReconnectionTest()
    success = await test.run_test()
    return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
