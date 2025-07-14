#!/usr/bin/env python3
"""
Comprehensive Reconnection Test Script

This script tests various reconnection scenarios to identify issues where players
disconnect during card play or hokm selection and cannot continue after reconnecting.

Test scenarios:
1. Disconnect during hokm selection phase (as hakem)
2. Disconnect during card play (your turn)
3. Disconnect during card play (not your turn)
4. Disconnect between tricks
5. Disconnect during team assignment
6. Multiple disconnect/reconnect cycles
"""

import asyncio
import websockets
import json
import sys
import os
import time
import random
from datetime import datetime

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from client_auth_manager import ClientAuthManager
    from game_states import GameState
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure this script is run from the project root directory")
    sys.exit(1)

SERVER_URI = "ws://192.168.1.26:8765"

class ReconnectionTester:
    def __init__(self, test_name, username="ReconnectTest"):
        self.test_name = test_name
        self.username = username
        self.player_id = None
        self.session_file = f".test_session_{test_name}_{int(time.time())}"
        self.auth_manager = ClientAuthManager()
        self.game_state = {}
        self.disconnection_points = []
        self.reconnection_results = []
        self.test_log = []
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {level}: {message}"
        self.test_log.append(log_entry)
        print(log_entry)
    
    def log_game_state(self, state_data):
        """Log current game state for debugging"""
        self.game_state.update(state_data)
        self.log(f"Game State Update: {state_data}", "STATE")
    
    async def authenticate(self, ws):
        """Handle authentication"""
        self.log("Starting authentication...")
        authenticated = await self.auth_manager.authenticate_with_server(ws)
        if authenticated:
            player_info = self.auth_manager.get_player_info()
            self.player_id = player_info['player_id']
            self.log(f"Authenticated as {player_info['username']} (ID: {self.player_id[:12]}...)")
            return True
        else:
            self.log("Authentication failed", "ERROR")
            return False
    
    async def save_session(self):
        """Save session for reconnection testing"""
        if self.player_id:
            try:
                with open(self.session_file, 'w') as f:
                    f.write(self.player_id)
                self.log(f"Session saved to {self.session_file}")
            except Exception as e:
                self.log(f"Failed to save session: {e}", "ERROR")
    
    async def load_session(self):
        """Load session for reconnection testing"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    session_player_id = f.read().strip()
                self.log(f"Loaded session: {session_player_id[:12]}...")
                return session_player_id
        except Exception as e:
            self.log(f"Failed to load session: {e}", "ERROR")
        return None
    
    async def cleanup_session(self):
        """Clean up test session file"""
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                self.log("Session file cleaned up")
        except:
            pass
    
    async def join_game(self, ws):
        """Join or reconnect to game"""
        session_player_id = await self.load_session()
        
        if session_player_id and session_player_id == self.player_id:
            self.log("Attempting reconnection...")
            await ws.send(json.dumps({
                "type": "reconnect",
                "player_id": session_player_id,
                "room_code": "9999"
            }))
        else:
            self.log("Joining as new player...")
            await ws.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
    
    async def simulate_disconnect(self, reason="testing"):
        """Record disconnection point for analysis"""
        disconnect_info = {
            "time": time.time(),
            "reason": reason,
            "game_state": self.game_state.copy()
        }
        self.disconnection_points.append(disconnect_info)
        self.log(f"Simulating disconnect: {reason}")
        await self.save_session()
    
    async def test_hokm_selection_reconnect(self):
        """Test reconnection during hokm selection phase"""
        self.log("=== Testing Hokm Selection Reconnection ===")
        
        async with websockets.connect(SERVER_URI) as ws:
            if not await self.authenticate(ws):
                return False
            
            await self.join_game(ws)
            
            # Wait for hokm selection phase
            hokm_selection_detected = False
            turn_count = 0
            max_turns = 50
            
            while turn_count < max_turns:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    self.log_game_state({"last_message": msg_type})
                    
                    if msg_type == 'join_success':
                        self.player_id = data.get('player_id')
                        await self.save_session()
                    
                    elif msg_type == 'initial_deal':
                        is_hakem = data.get('is_hakem', False)
                        if is_hakem:
                            self.log("I am the hakem - hokm selection phase detected!")
                            hokm_selection_detected = True
                            
                            # Simulate disconnect during hokm selection
                            await self.simulate_disconnect("during_hokm_selection")
                            break
                        else:
                            self.log("Waiting for hakem to select hokm...")
                    
                    elif msg_type == 'hokm_selected':
                        self.log("Hokm already selected, continuing to next test...")
                        break
                    
                    elif msg_type == 'error':
                        self.log(f"Server error: {data.get('message')}", "ERROR")
                        
                    turn_count += 1
                    
                except asyncio.TimeoutError:
                    self.log("Timeout waiting for messages", "WARNING")
                    turn_count += 1
                except Exception as e:
                    self.log(f"Error in hokm selection test: {e}", "ERROR")
                    break
            
            if not hokm_selection_detected:
                self.log("Hokm selection phase not detected in this session", "WARNING")
                return False
        
        # Test reconnection after disconnect
        self.log("Testing reconnection after hokm selection disconnect...")
        await asyncio.sleep(2)  # Brief pause
        
        async with websockets.connect(SERVER_URI) as ws:
            if not await self.authenticate(ws):
                return False
            
            await self.join_game(ws)
            
            reconnection_success = False
            turn_count = 0
            
            while turn_count < 30:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    if msg_type == 'reconnect_success':
                        self.log("✅ Reconnection successful!")
                        game_state_data = data.get('game_state', {})
                        phase = game_state_data.get('phase', 'unknown')
                        self.log(f"Reconnected to phase: {phase}")
                        
                        # Check if we can still select hokm
                        if phase == 'hokm_selection':
                            self.log("Still in hokm selection phase - testing hokm selection...")
                            # Try to select hokm
                            await ws.send(json.dumps({
                                'type': 'hokm_selected',
                                'suit': 'hearts',
                                'room_code': '9999'
                            }))
                            self.log("Hokm selection command sent")
                        
                        reconnection_success = True
                        break
                    
                    elif msg_type == 'error':
                        error_msg = data.get('message', '')
                        self.log(f"Reconnection error: {error_msg}", "ERROR")
                        if "reconnect" in error_msg.lower():
                            break
                    
                    elif msg_type == 'initial_deal':
                        is_hakem = data.get('is_hakem', False)
                        if is_hakem:
                            self.log("Received initial deal again - testing hokm selection...")
                            await ws.send(json.dumps({
                                'type': 'hokm_selected',
                                'suit': 'spades',
                                'room_code': '9999'
                            }))
                    
                    turn_count += 1
                    
                except asyncio.TimeoutError:
                    self.log("Timeout during reconnection test", "WARNING")
                    break
                except Exception as e:
                    self.log(f"Error during reconnection test: {e}", "ERROR")
                    break
            
            self.reconnection_results.append({
                "test": "hokm_selection",
                "success": reconnection_success,
                "details": "Successfully reconnected and could select hokm" if reconnection_success else "Failed to reconnect or continue hokm selection"
            })
            
            return reconnection_success
    
    async def test_card_play_reconnect(self):
        """Test reconnection during card play phase"""
        self.log("=== Testing Card Play Reconnection ===")
        
        async with websockets.connect(SERVER_URI) as ws:
            if not await self.authenticate(ws):
                return False
            
            await self.join_game(ws)
            
            card_play_detected = False
            turn_count = 0
            max_turns = 100
            
            while turn_count < max_turns:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    self.log_game_state({"last_message": msg_type})
                    
                    if msg_type == 'join_success' or msg_type == 'reconnect_success':
                        if 'player_id' in data:
                            self.player_id = data.get('player_id')
                            await self.save_session()
                    
                    elif msg_type == 'turn_start':
                        your_turn = data.get('your_turn', False)
                        current_player = data.get('current_player')
                        hand = data.get('hand', [])
                        
                        self.log(f"Turn start - Current player: {current_player}, Your turn: {your_turn}, Hand size: {len(hand)}")
                        
                        if your_turn and hand:
                            self.log("My turn detected - simulating disconnect during card play!")
                            card_play_detected = True
                            await self.simulate_disconnect("during_my_turn")
                            break
                        elif hand:
                            self.log(f"Waiting for {current_player} to play...")
                    
                    elif msg_type == 'initial_deal':
                        is_hakem = data.get('is_hakem', False)
                        if is_hakem:
                            # Auto-select hokm to get to card play faster
                            await ws.send(json.dumps({
                                'type': 'hokm_selected',
                                'suit': 'hearts',
                                'room_code': '9999'
                            }))
                            self.log("Auto-selected hearts as hokm to progress to card play")
                    
                    elif msg_type == 'error':
                        self.log(f"Server error: {data.get('message')}", "ERROR")
                    
                    turn_count += 1
                    
                except asyncio.TimeoutError:
                    self.log("Timeout waiting for card play phase", "WARNING")
                    turn_count += 1
                except Exception as e:
                    self.log(f"Error in card play test: {e}", "ERROR")
                    break
            
            if not card_play_detected:
                self.log("Card play phase not reached in this session", "WARNING")
                return False
        
        # Test reconnection after disconnect during card play
        self.log("Testing reconnection after card play disconnect...")
        await asyncio.sleep(2)
        
        async with websockets.connect(SERVER_URI) as ws:
            if not await self.authenticate(ws):
                return False
            
            await self.join_game(ws)
            
            reconnection_success = False
            can_play_card = False
            turn_count = 0
            
            while turn_count < 30:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    if msg_type == 'reconnect_success':
                        self.log("✅ Reconnection successful!")
                        game_state_data = data.get('game_state', {})
                        phase = game_state_data.get('phase', 'unknown')
                        hand = game_state_data.get('hand', [])
                        self.log(f"Reconnected to phase: {phase}, Hand size: {len(hand)}")
                        reconnection_success = True
                    
                    elif msg_type == 'turn_start':
                        your_turn = data.get('your_turn', False)
                        hand = data.get('hand', [])
                        
                        if your_turn and hand and reconnection_success:
                            self.log("Can play card after reconnection - testing card play...")
                            # Try to play first card
                            card = hand[0]
                            await ws.send(json.dumps({
                                "type": "play_card",
                                "room_code": "9999",
                                "player_id": self.player_id,
                                "card": card
                            }))
                            self.log(f"Attempted to play card: {card}")
                            can_play_card = True
                            break
                    
                    elif msg_type == 'card_played':
                        if data.get('player_id') == self.player_id:
                            self.log("✅ Successfully played card after reconnection!")
                            can_play_card = True
                            break
                    
                    elif msg_type == 'error':
                        error_msg = data.get('message', '')
                        self.log(f"Error during card play test: {error_msg}", "ERROR")
                        if "reconnect" in error_msg.lower():
                            break
                    
                    turn_count += 1
                    
                except asyncio.TimeoutError:
                    self.log("Timeout during card play reconnection test", "WARNING")
                    break
                except Exception as e:
                    self.log(f"Error during card play reconnection: {e}", "ERROR")
                    break
            
            self.reconnection_results.append({
                "test": "card_play",
                "success": reconnection_success and can_play_card,
                "details": f"Reconnection: {reconnection_success}, Can play card: {can_play_card}"
            })
            
            return reconnection_success and can_play_card
    
    async def test_multiple_reconnections(self):
        """Test multiple disconnect/reconnect cycles"""
        self.log("=== Testing Multiple Reconnections ===")
        
        reconnect_count = 0
        max_reconnects = 3
        success_count = 0
        
        for i in range(max_reconnects):
            self.log(f"Reconnection attempt {i+1}/{max_reconnects}")
            
            async with websockets.connect(SERVER_URI) as ws:
                if not await self.authenticate(ws):
                    continue
                
                await self.join_game(ws)
                
                # Wait briefly and then disconnect
                await asyncio.sleep(3)
                await self.simulate_disconnect(f"multiple_test_{i+1}")
                reconnect_count += 1
            
            # Brief pause between reconnections
            await asyncio.sleep(1)
            
            # Try to reconnect
            async with websockets.connect(SERVER_URI) as ws:
                if not await self.authenticate(ws):
                    continue
                
                await self.join_game(ws)
                
                reconnected = False
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    if data.get('type') in ['reconnect_success', 'join_success']:
                        self.log(f"✅ Reconnection {i+1} successful")
                        success_count += 1
                        reconnected = True
                except:
                    self.log(f"❌ Reconnection {i+1} failed")
                
                if not reconnected:
                    break
        
        success_rate = (success_count / reconnect_count) * 100 if reconnect_count > 0 else 0
        self.reconnection_results.append({
            "test": "multiple_reconnections",
            "success": success_count == reconnect_count,
            "details": f"Success rate: {success_rate:.1f}% ({success_count}/{reconnect_count})"
        })
        
        return success_count == reconnect_count
    
    def generate_report(self):
        """Generate comprehensive test report"""
        report = []
        report.append("="*60)
        report.append(f"RECONNECTION TEST REPORT - {self.test_name}")
        report.append("="*60)
        report.append(f"Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Username: {self.username}")
        report.append(f"Player ID: {self.player_id[:12] if self.player_id else 'None'}...")
        report.append("")
        
        # Test results summary
        report.append("TEST RESULTS:")
        report.append("-" * 40)
        total_tests = len(self.reconnection_results)
        passed_tests = sum(1 for r in self.reconnection_results if r['success'])
        
        for result in self.reconnection_results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            report.append(f"{result['test']:20} | {status} | {result['details']}")
        
        report.append("")
        report.append(f"Overall Result: {passed_tests}/{total_tests} tests passed")
        report.append("")
        
        # Disconnection points
        if self.disconnection_points:
            report.append("DISCONNECTION POINTS:")
            report.append("-" * 40)
            for i, dp in enumerate(self.disconnection_points):
                report.append(f"{i+1}. {dp['reason']} - Game state: {dp['game_state']}")
            report.append("")
        
        # Detailed log
        report.append("DETAILED LOG:")
        report.append("-" * 40)
        for log_entry in self.test_log[-20:]:  # Last 20 entries
            report.append(log_entry)
        
        report.append("="*60)
        
        return "\n".join(report)
    
    async def run_all_tests(self):
        """Run all reconnection tests"""
        self.log(f"Starting comprehensive reconnection tests for {self.test_name}")
        
        try:
            # Test 1: Hokm selection reconnection
            await self.test_hokm_selection_reconnect()
            await asyncio.sleep(3)
            
            # Test 2: Card play reconnection  
            await self.test_card_play_reconnect()
            await asyncio.sleep(3)
            
            # Test 3: Multiple reconnections
            await self.test_multiple_reconnections()
            
        except Exception as e:
            self.log(f"Test suite error: {e}", "ERROR")
        finally:
            await self.cleanup_session()
        
        # Generate and save report
        report = self.generate_report()
        
        # Save report to file
        report_file = f"reconnection_test_report_{self.test_name}_{int(time.time())}.txt"
        try:
            with open(report_file, 'w') as f:
                f.write(report)
            self.log(f"Report saved to {report_file}")
        except Exception as e:
            self.log(f"Failed to save report: {e}", "ERROR")
        
        print("\n" + report)
        
        return len([r for r in self.reconnection_results if r['success']]) == len(self.reconnection_results)

async def main():
    """Main test function"""
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
    else:
        test_name = f"reconnect_test_{int(time.time())}"
    
    print(f"🔧 Starting Comprehensive Reconnection Tests")
    print(f"📝 Test Name: {test_name}")
    print(f"🌐 Server: {SERVER_URI}")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    tester = ReconnectionTester(test_name)
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 All reconnection tests passed!")
        return 0
    else:
        print("\n❌ Some reconnection tests failed!")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        sys.exit(1)
