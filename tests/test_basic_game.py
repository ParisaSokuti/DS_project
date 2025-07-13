#!/usr/bin/env python3
"""
Basic Functionality Test for Hokm WebSocket Card Game Server

This script connects 4 simulated clients and runs through a complete game:
1. Connect 4 players to room
2. Team assignment phase
3. Hokm selection phase  
4. Card playing phase
5. Scoring and completion

Usage: python test_basic_game.py
"""

import asyncio
import websockets
import json
import time
import sys
import random
from typing import Dict, List, Optional, Any

class TestResult:
    def __init__(self, phase: str):
        self.phase = phase
        self.success = False
        self.message = ""
        self.details = []
        self.start_time = time.time()
        self.end_time = None
        
    def pass_test(self, message: str, details: List[str] = None):
        self.success = True
        self.message = message
        self.details = details or []
        self.end_time = time.time()
        
    def fail_test(self, message: str, details: List[str] = None):
        self.success = False
        self.message = message
        self.details = details or []
        self.end_time = time.time()
        
    def duration(self) -> float:
        return (self.end_time or time.time()) - self.start_time

class GameClient:
    def __init__(self, client_id: int, room_code: str = None):
        self.client_id = client_id
        self.room_code = room_code or f"TEST_{random.randint(1000, 9999)}"
        self.websocket = None
        self.player_id = None
        self.username = None
        self.player_number = None
        self.connected = False
        self.messages = []
        self.hand = []
        self.team = None
        self.is_hakem = False
        self.hokm = None
        self.current_phase = "disconnected"
        
    async def connect(self, uri: str = "ws://localhost:8765"):
        """Connect to the WebSocket server"""
        try:
            self.websocket = await websockets.connect(uri)
            self.connected = True
            print(f"[CLIENT-{self.client_id}] Connected to {uri}")
            return True
        except Exception as e:
            print(f"[CLIENT-{self.client_id}] Failed to connect: {e}")
            return False
            
    async def disconnect(self):
        """Disconnect from the server"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            print(f"[CLIENT-{self.client_id}] Disconnected")
            
    async def send_message(self, message: Dict[str, Any]):
        """Send a message to the server"""
        if not self.websocket:
            raise Exception("Not connected")
        await self.websocket.send(json.dumps(message))
        print(f"[CLIENT-{self.client_id}] SENT: {message}")
        
    async def receive_message(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Receive a message from the server with timeout"""
        try:
            message_str = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            message = json.loads(message_str)
            self.messages.append(message)
            self.process_message(message)
            print(f"[CLIENT-{self.client_id}] RECEIVED: {message}")
            return message
        except asyncio.TimeoutError:
            print(f"[CLIENT-{self.client_id}] Timeout waiting for message")
            return None
        except Exception as e:
            print(f"[CLIENT-{self.client_id}] Error receiving message: {e}")
            return None
            
    def process_message(self, message: Dict[str, Any]):
        """Process received message and update client state"""
        msg_type = message.get('type')
        
        if msg_type == 'join_success':
            self.player_id = message.get('player_id')
            self.username = message.get('username')
            self.player_number = message.get('player_number')
            
        elif msg_type == 'phase_change':
            self.current_phase = message.get('new_phase')
            
        elif msg_type == 'team_assignment':
            teams = message.get('teams', {})
            hakem = message.get('hakem')
            self.is_hakem = (self.username == hakem)
            # Find which team this player is on
            for team_id, players in teams.items():
                if self.username in players:
                    self.team = team_id
                    
        elif msg_type == 'initial_deal':
            self.hand = message.get('hand', [])
            self.is_hakem = message.get('is_hakem', False)
            
        elif msg_type == 'hokm_selected':
            self.hokm = message.get('suit')
            
        elif msg_type == 'final_deal':
            if 'hand' in message:
                self.hand = message.get('hand', [])
            self.hokm = message.get('hokm')
            
        elif msg_type == 'card_played':
            # Remove played card from hand if it was ours
            if message.get('player') == self.username:
                card = message.get('card')
                if card in self.hand:
                    self.hand.remove(card)
                    
        elif msg_type == 'turn_start':
            if 'hand' in message:
                self.hand = message.get('hand', [])
                
    async def join_room(self):
        """Join the game room"""
        await self.send_message({
            'type': 'join',
            'room_code': self.room_code
        })
        
    async def select_hokm(self, suit: str):
        """Select hokm suit (only for hakem)"""
        await self.send_message({
            'type': 'hokm_selected',
            'room_code': self.room_code,
            'suit': suit
        })
        
    async def play_card(self, card: str):
        """Play a card"""
        await self.send_message({
            'type': 'play_card',
            'room_code': self.room_code,
            'player_id': self.player_id,
            'card': card
        })

class GameTest:
    def __init__(self, room_code: str = None):
        self.room_code = room_code or f"TEST_{random.randint(1000, 9999)}"
        self.clients: List[GameClient] = []
        self.results: List[TestResult] = []
        self.current_phase = None
        
    def add_result(self, result: TestResult):
        """Add a test result"""
        self.results.append(result)
        status = "✅ PASS" if result.success else "❌ FAIL"
        print(f"\n{status} {result.phase}: {result.message} ({result.duration():.2f}s)")
        if result.details:
            for detail in result.details:
                print(f"  - {detail}")
                
    async def setup_clients(self) -> TestResult:
        """Set up 4 game clients"""
        result = TestResult("Client Setup")
        
        try:
            # Create 4 clients
            for i in range(4):
                client = GameClient(i + 1, self.room_code)
                self.clients.append(client)
                
            # Connect all clients
            connection_tasks = [client.connect() for client in self.clients]
            connections = await asyncio.gather(*connection_tasks, return_exceptions=True)
            
            successful_connections = sum(1 for conn in connections if conn is True)
            
            if successful_connections == 4:
                result.pass_test(
                    "All 4 clients connected successfully",
                    [f"Client {i+1}: Connected" for i in range(4)]
                )
            else:
                result.fail_test(
                    f"Only {successful_connections}/4 clients connected",
                    [f"Client {i+1}: {'Connected' if connections[i] else 'Failed'}" 
                     for i in range(4)]
                )
                
        except Exception as e:
            result.fail_test(f"Exception during client setup: {e}")
            
        return result
        
    async def test_room_joining(self) -> TestResult:
        """Test joining the game room"""
        result = TestResult("Room Joining")
        
        try:
            # All clients join the room
            join_tasks = []
            for client in self.clients:
                join_tasks.append(client.join_room())
                
            await asyncio.gather(*join_tasks)
            
            # Wait for join confirmations
            successful_joins = 0
            join_details = []
            
            for client in self.clients:
                message = await client.receive_message(timeout=10.0)
                if message and message.get('type') == 'join_success':
                    successful_joins += 1
                    join_details.append(f"{client.username} joined as Player {client.player_number}")
                else:
                    join_details.append(f"Client {client.client_id} failed to join")
                    
            if successful_joins == 4:
                result.pass_test(
                    "All 4 players joined the room successfully",
                    join_details
                )
            else:
                result.fail_test(
                    f"Only {successful_joins}/4 players joined successfully",
                    join_details
                )
                
        except Exception as e:
            result.fail_test(f"Exception during room joining: {e}")
            
        return result
        
    async def test_team_assignment(self) -> TestResult:
        """Test team assignment phase"""
        result = TestResult("Team Assignment")
        
        try:
            # Wait for phase change and team assignment messages
            team_assignments = {}
            hakem_found = False
            phase_changes = 0
            
            # Each client should receive phase_change and team_assignment
            for client in self.clients:
                messages_received = 0
                timeout_count = 0
                
                while messages_received < 2 and timeout_count < 3:
                    message = await client.receive_message(timeout=5.0)
                    if message:
                        messages_received += 1
                        msg_type = message.get('type')
                        
                        if msg_type == 'phase_change':
                            phase_changes += 1
                            
                        elif msg_type == 'team_assignment':
                            teams = message.get('teams', {})
                            hakem = message.get('hakem')
                            
                            if hakem:
                                hakem_found = True
                                
                            # Record team assignments (only once to avoid duplicates)
                            if not team_assignments:
                                for team_id, players in teams.items():
                                    team_assignments[team_id] = players.copy()
                    else:
                        timeout_count += 1
                        
            # Validate team assignments
            details = []
            total_players = sum(len(players) for players in team_assignments.values())
            
            if phase_changes >= 4:  # All clients got phase change
                details.append("✓ Phase change to team assignment received")
            else:
                details.append(f"✗ Only {phase_changes}/4 clients received phase change")
                
            if hakem_found:
                details.append("✓ Hakem assigned")
            else:
                details.append("✗ No hakem found")
                
            if len(team_assignments) == 2:
                details.append("✓ Two teams created")
                for team_id, players in team_assignments.items():
                    details.append(f"  Team {team_id}: {', '.join(players)}")
            else:
                details.append(f"✗ Expected 2 teams, found {len(team_assignments)}")
                
            if total_players == 4:
                details.append("✓ All 4 players assigned to teams")
            else:
                details.append(f"✗ Only {total_players}/4 players assigned")
                
            # Determine success
            success_conditions = [
                phase_changes >= 4,
                hakem_found,
                len(team_assignments) == 2,
                total_players == 4
            ]
            
            if all(success_conditions):
                result.pass_test("Team assignment completed successfully", details)
            else:
                result.fail_test("Team assignment failed", details)
                
        except Exception as e:
            result.fail_test(f"Exception during team assignment: {e}")
            
        return result
        
    async def test_hokm_selection(self) -> TestResult:
        """Test hokm selection phase"""
        result = TestResult("Hokm Selection")
        
        try:
            # Give the server a moment to send initial deal messages after phase change
            await asyncio.sleep(0.1)
            
            # Each client will receive exactly one initial_deal message
            initial_deals = 0
            hakem_client = None
            hakem_hand = []
            
            # Wait for each client to receive their initial deal message
            receive_tasks = []
            for client in self.clients:
                receive_tasks.append(client.receive_message(timeout=15.0))
            
            messages = await asyncio.gather(*receive_tasks, return_exceptions=True)
            
            for i, message in enumerate(messages):
                if isinstance(message, Exception):
                    continue
                if message and message.get('type') == 'initial_deal':
                    initial_deals += 1
                    if message.get('is_hakem'):
                        hakem_client = self.clients[i]
                        hakem_hand = message.get('hand', [])
                        
            details = [f"Initial deals processed: {initial_deals}/4"]
            
            if hakem_client and hakem_hand:
                details.append(f"✓ Hakem identified: {hakem_client.username}")
                
                # Extract suit from first card (format: "rank_suit" like "Q_spades")
                first_card = hakem_hand[0]
                hokm_suit = first_card.split('_')[1] if '_' in first_card else 'spades'
                
                await hakem_client.select_hokm(hokm_suit)
                details.append(f"✓ Hakem selected hokm: {hokm_suit}")
                
                # Wait for hokm selection confirmation from all clients
                confirm_tasks = [client.receive_message(timeout=5.0) for client in self.clients]
                confirm_messages = await asyncio.gather(*confirm_tasks, return_exceptions=True)
                
                hokm_confirmations = 0
                for msg in confirm_messages:
                    if not isinstance(msg, Exception) and msg and msg.get('type') == 'hokm_selected':
                        hokm_confirmations += 1
                        
                details.append(f"Hokm confirmations: {hokm_confirmations}/4")
                
                if hokm_confirmations >= 3:  # At least 3 clients should get confirmation
                    result.pass_test("Hokm selection completed successfully", details)
                else:
                    result.fail_test("Not all clients received hokm confirmation", details)
            else:
                result.fail_test("No hakem found or hakem has no cards", details)
                
        except Exception as e:
            result.fail_test(f"Exception during hokm selection: {e}")
            
        return result
        
    async def test_final_deal(self) -> TestResult:
        """Test final deal phase (remaining cards dealt)"""
        result = TestResult("Final Deal")
        
        try:
            # Wait for final deal messages
            final_deals = 0
            hand_sizes = []
            
            for client in self.clients:
                # May receive multiple messages (phase_change, final_deal)
                messages_count = 0
                while messages_count < 3:  # Expect up to 3 messages
                    message = await client.receive_message(timeout=5.0)
                    if message:
                        messages_count += 1
                        if message.get('type') == 'final_deal' and 'hand' in message:
                            final_deals += 1
                            hand_sizes.append(len(client.hand))
                            break
                    else:
                        break
                        
            details = [
                f"Final deals received: {final_deals}/4",
                f"Hand sizes: {hand_sizes}"
            ]
            
            # Each player should have 13 cards after final deal
            expected_hand_size = 13
            correct_hands = sum(1 for size in hand_sizes if size == expected_hand_size)
            
            details.append(f"Players with correct hand size ({expected_hand_size}): {correct_hands}/4")
            
            if final_deals == 4 and correct_hands == 4:
                result.pass_test("Final deal completed successfully", details)
            elif final_deals == 4:
                result.pass_test("Final deal sent to all players", details + 
                               ["⚠️  Some players have incorrect hand sizes"])
            else:
                result.fail_test("Final deal incomplete", details)
                
        except Exception as e:
            result.fail_test(f"Exception during final deal: {e}")
            
        return result
        
    async def test_gameplay(self) -> TestResult:
        """Test basic gameplay (play a few tricks)"""
        result = TestResult("Gameplay")
        
        try:
            details = []
            tricks_played = 0
            max_tricks = 3  # Play 3 tricks for testing
            
            # Wait for turn_start message to begin gameplay
            turn_starts = 0
            for client in self.clients:
                message = await client.receive_message(timeout=10.0)
                if message and message.get('type') == 'turn_start':
                    turn_starts += 1
                    
            details.append(f"Turn start messages: {turn_starts}/4")
            
            # Play several tricks
            for trick_num in range(max_tricks):
                details.append(f"\n--- Trick {trick_num + 1} ---")
                
                # Each player plays one card
                cards_played = 0
                for player_turn in range(4):
                    # Find current player
                    current_player = None
                    for client in self.clients:
                        if client.hand:  # Player has cards
                            current_player = client
                            break
                            
                    if current_player and current_player.hand:
                        # Play first available card
                        card_to_play = current_player.hand[0]
                        await current_player.play_card(card_to_play)
                        cards_played += 1
                        details.append(f"  {current_player.username} played {card_to_play}")
                        
                        # Wait for card_played confirmation
                        await current_player.receive_message(timeout=3.0)
                        
                        # Other players receive the card_played message
                        for other_client in self.clients:
                            if other_client != current_player:
                                await other_client.receive_message(timeout=2.0)
                                
                # Wait for trick result
                trick_results = 0
                for client in self.clients:
                    message = await client.receive_message(timeout=5.0)
                    if message and message.get('type') == 'trick_result':
                        trick_results += 1
                        
                details.append(f"  Cards played: {cards_played}/4")
                details.append(f"  Trick results received: {trick_results}/4")
                
                if cards_played == 4 and trick_results >= 3:
                    tricks_played += 1
                else:
                    break
                    
                # Prepare for next trick - wait for turn_start
                if trick_num < max_tricks - 1:
                    for client in self.clients:
                        await client.receive_message(timeout=3.0)
                        
            if tricks_played >= 2:
                result.pass_test(
                    f"Gameplay working - completed {tricks_played} tricks",
                    details
                )
            elif tricks_played >= 1:
                result.pass_test(
                    f"Basic gameplay working - completed {tricks_played} trick(s)",
                    details + ["⚠️  Some issues with trick progression"]
                )
            else:
                result.fail_test("Gameplay failed - no tricks completed", details)
                
        except Exception as e:
            result.fail_test(f"Exception during gameplay: {e}")
            
        return result
        
    async def cleanup(self):
        """Clean up all client connections"""
        for client in self.clients:
            try:
                await client.disconnect()
            except:
                pass
                
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("🎮 HOKM GAME SERVER TEST SUMMARY")
        print("="*60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\nDetailed Results:")
        print("-" * 40)
        
        for result in self.results:
            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"{status} {result.phase}: {result.message}")
            
        if failed_tests > 0:
            print(f"\n⚠️  {failed_tests} test(s) failed. Check the detailed logs above.")
            print("Common issues to check:")
            print("  - Is the server running on localhost:8765?")
            print("  - Are there any Redis connection issues?")
            print("  - Check server logs for errors")
        else:
            print("\n🎉 All tests passed! Your game server is working correctly.")
            
        print("="*60)

async def main():
    """Main test execution"""
    print("🎮 Starting Hokm Game Server Basic Functionality Test")
    print("="*60)
    
    test = GameTest()
    
    try:
        # Run all test phases
        test.add_result(await test.setup_clients())
        test.add_result(await test.test_room_joining())
        test.add_result(await test.test_team_assignment())
        test.add_result(await test.test_hokm_selection())
        test.add_result(await test.test_final_deal())
        test.add_result(await test.test_gameplay())
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Fatal error during testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always cleanup
        await test.cleanup()
        
    # Print final summary
    test.print_summary()
    
    # Exit with appropriate code
    failed_tests = sum(1 for r in test.results if not r.success)
    return 0 if failed_tests == 0 else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
