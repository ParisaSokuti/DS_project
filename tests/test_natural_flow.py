#!/usr/bin/env python3
"""
Natural Flow Test for Hokm WebSocket Card Game Server
This test follows the natural message flow from the server instead of forcing separate phases.
"""

import asyncio
import websockets
import json
import random
import time
from typing import List, Dict, Optional

class TestClient:
    def __init__(self, client_id: int, room_code: str):
        self.client_id = client_id
        self.username = f"Player {client_id}"
        self.room_code = room_code
        self.websocket = None
        self.player_id = None
        self.hand = []
        self.is_hakem = False
        self.team = None
        self.hokm = None
        
    async def connect(self):
        """Connect to server"""
        self.websocket = await websockets.connect("ws://localhost:8765")
        print(f"[{self.username}] Connected")
        
    async def join_room(self):
        """Join the game room"""
        await self.send_message({
            'type': 'join',
            'room_code': self.room_code
        })
        
    async def send_message(self, message: dict):
        """Send a message to server"""
        if self.websocket:
            await self.websocket.send(json.dumps(message))
            print(f"[{self.username}] SENT: {message}")
            
    async def receive_message(self, timeout: float = 30.0):
        """Receive and process a message from server"""
        try:
            message_str = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            message = json.loads(message_str)
            print(f"[{self.username}] RECEIVED: {message}")
            
            # Update client state based on message
            msg_type = message.get('type')
            if msg_type == 'join_success':
                self.player_id = message.get('player_id')
            elif msg_type == 'team_assignment':
                teams = message.get('teams', {})
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
                
            return message
        except asyncio.TimeoutError:
            print(f"[{self.username}] Timeout waiting for message")
            return None
        except Exception as e:
            print(f"[{self.username}] Error receiving message: {e}")
            return None
            
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
        
    async def disconnect(self):
        """Disconnect from server"""
        if self.websocket:
            await self.websocket.close()
            print(f"[{self.username}] Disconnected")

class NaturalFlowTest:
    def __init__(self):
        self.room_code = f"TEST_{random.randint(1000, 9999)}"
        self.clients: List[TestClient] = []
        self.test_results = []
        
    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log a test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append((test_name, success))
        print(f"\n{status} {test_name}: {details}")
        
    async def setup_clients(self):
        """Create and connect 4 clients"""
        print("🎮 Setting up clients...")
        
        for i in range(1, 5):
            client = TestClient(i, self.room_code)
            self.clients.append(client)
            await client.connect()
            await client.join_room()
            
        self.log_result("Client Setup", True, "All 4 clients connected and joined")
        
    async def run_natural_flow_test(self):
        """Run the test following natural message flow"""
        print(f"\n🎮 Starting Natural Flow Test (Room: {self.room_code})")
        
        try:
            # Step 1: Setup
            await self.setup_clients()
            
            # Step 2: Process all messages in natural order
            messages_processed = 0
            phase = "waiting_for_join_success"
            join_success_count = 0
            team_assignment_received = False
            initial_deals_received = 0
            hakem_client = None
            hokm_confirmations = 0
            final_deals_received = 0
            gameplay_started = False
            
            # Keep processing messages until we complete the full flow or timeout
            timeout_start = time.time()
            max_test_time = 120  # 2 minutes max
            
            while time.time() - timeout_start < max_test_time:
                # Receive messages from all clients simultaneously
                receive_tasks = []
                for client in self.clients:
                    receive_tasks.append(client.receive_message(timeout=5.0))
                    
                messages = await asyncio.gather(*receive_tasks, return_exceptions=True)
                
                any_message_received = False
                for i, message in enumerate(messages):
                    if isinstance(message, Exception) or message is None:
                        continue
                        
                    any_message_received = True
                    messages_processed += 1
                    msg_type = message.get('type')
                    client = self.clients[i]
                    
                    # Process based on message type and current phase
                    if msg_type == 'join_success' and phase == "waiting_for_join_success":
                        join_success_count += 1
                        if join_success_count == 4:
                            self.log_result("Room Joining", True, "All 4 players joined successfully")
                            phase = "waiting_for_team_assignment"
                            
                    elif msg_type == 'team_assignment' and phase == "waiting_for_team_assignment":
                        if not team_assignment_received:
                            team_assignment_received = True
                            teams = message.get('teams', {})
                            hakem = message.get('hakem')
                            total_players = sum(len(players) for players in teams.values())
                            success = len(teams) == 2 and total_players == 4 and hakem
                            self.log_result("Team Assignment", success, 
                                          f"Teams: {teams}, Hakem: {hakem}")
                            phase = "waiting_for_initial_deals"
                            
                    elif msg_type == 'initial_deal' and phase == "waiting_for_initial_deals":
                        initial_deals_received += 1
                        if message.get('is_hakem'):
                            hakem_client = client
                            
                        if initial_deals_received == 4:
                            self.log_result("Initial Deal", True, 
                                          f"All players received initial hands")
                            phase = "waiting_for_hokm_selection"
                            
                            # Hakem selects hokm
                            if hakem_client and hakem_client.hand:
                                first_card = hakem_client.hand[0]
                                hokm_suit = first_card.split('_')[1] if '_' in first_card else 'spades'
                                await hakem_client.select_hokm(hokm_suit)
                                print(f"[TEST] Hakem {hakem_client.username} selected hokm: {hokm_suit}")
                                
                    elif msg_type == 'hokm_selected' and phase == "waiting_for_hokm_selection":
                        hokm_confirmations += 1
                        if hokm_confirmations >= 4:  # All clients got confirmation
                            self.log_result("Hokm Selection", True,
                                          f"Hokm selected and confirmed by all players")
                            phase = "waiting_for_final_deals"
                            
                    elif msg_type == 'final_deal' and phase == "waiting_for_final_deals":
                        # Count final deals that actually contain hand data
                        if 'hand' in message:
                            final_deals_received += 1
                            
                        if final_deals_received >= 4:
                            hand_sizes = [len(client.hand) for client in self.clients]
                            correct_hands = sum(1 for size in hand_sizes if size == 13)
                            success = correct_hands == 4
                            self.log_result("Final Deal", success,
                                          f"Hand sizes: {hand_sizes}, Correct (13): {correct_hands}/4")
                            phase = "waiting_for_gameplay"
                            
                    elif msg_type == 'turn_start' and phase == "waiting_for_gameplay":
                        if not gameplay_started:
                            gameplay_started = True
                            self.log_result("Gameplay Start", True, "First turn started")
                            # End the test here successfully
                            return True
                            
                # If no messages received in this round, break to avoid infinite loop
                if not any_message_received:
                    break
                    
            # Test timed out or failed
            self.log_result("Overall Test", False, f"Test incomplete after {messages_processed} messages")
            return False
            
        except Exception as e:
            self.log_result("Overall Test", False, f"Exception: {e}")
            return False
            
    async def cleanup(self):
        """Cleanup all clients"""
        for client in self.clients:
            await client.disconnect()
            
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("🎮 NATURAL FLOW TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, success in self.test_results if success)
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%" if total > 0 else "No tests run")
        
        print("\nDetailed Results:")
        print("-" * 40)
        for test_name, success in self.test_results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name}")

async def main():
    test = NaturalFlowTest()
    
    try:
        success = await test.run_natural_flow_test()
        exit_code = 0 if success else 1
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        exit_code = 130
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        exit_code = 1
    finally:
        await test.cleanup()
        
    test.print_summary()
    exit(exit_code)

if __name__ == "__main__":
    asyncio.run(main())
