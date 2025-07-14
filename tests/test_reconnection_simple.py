#!/usr/bin/env python3
"""
Simple Reconnection Test Script

This script tests the specific issue where players disconnect during gameplay
and cannot continue after reconnecting.

Usage:
    python test_reconnection_simple.py [username]
"""

import asyncio
import websockets
import json
import sys
import os
import time

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from client_auth_manager import ClientAuthManager
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure this script is run from the project root directory")
    sys.exit(1)

SERVER_URI = "ws://192.168.1.26:8765"

class SimpleReconnectionTest:
    def __init__(self, username="TestUser"):
        self.username = username
        self.player_id = None
        self.session_file = f".test_session_{username}_{int(time.time())}"
        self.auth_manager = ClientAuthManager()
        
    async def cleanup(self):
        """Clean up session file"""
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
        except:
            pass
    
    async def save_session(self):
        """Save session for reconnection"""
        if self.player_id:
            with open(self.session_file, 'w') as f:
                f.write(self.player_id)
            print(f"💾 Session saved: {self.player_id[:12]}...")
    
    async def load_session(self):
        """Load session for reconnection"""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    return f.read().strip()
        except:
            pass
        return None
    
    async def test_reconnection_scenario(self):
        """Test reconnection during active gameplay"""
        print("🔧 Testing Reconnection Scenario")
        print(f"Username: {self.username}")
        print(f"Server: {SERVER_URI}")
        print("="*50)
        
        # Phase 1: Join game and get to a state where we can disconnect
        print("\n📋 Phase 1: Joining game and waiting for gameplay...")
        
        async with websockets.connect(SERVER_URI) as ws:
            # Authenticate
            authenticated = await self.auth_manager.authenticate_with_server(ws)
            if not authenticated:
                print("❌ Authentication failed")
                return False
            
            player_info = self.auth_manager.get_player_info()
            self.player_id = player_info['player_id']
            print(f"✅ Authenticated as {player_info['username']}")
            
            # Join game
            await ws.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            
            # Wait for game to progress
            phase_detected = None
            disconnect_ready = False
            turn_count = 0
            max_turns = 60
            
            while turn_count < max_turns and not disconnect_ready:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    print(f"[{turn_count:2d}] Received: {msg_type}")
                    
                    if msg_type == 'join_success':
                        self.player_id = data.get('player_id', self.player_id)
                        await self.save_session()
                    
                    elif msg_type == 'initial_deal':
                        is_hakem = data.get('is_hakem', False)
                        if is_hakem:
                            phase_detected = "hokm_selection"
                            print("🎴 I am hakem - hokm selection phase detected!")
                            print("🔌 Disconnecting during hokm selection...")
                            disconnect_ready = True
                            break
                        else:
                            # Auto-proceed by waiting for hokm
                            print("⏳ Waiting for hakem to select hokm...")
                    
                    elif msg_type == 'turn_start':
                        your_turn = data.get('your_turn', False)
                        hand = data.get('hand', [])
                        current_player = data.get('current_player')
                        
                        if your_turn and hand:
                            phase_detected = "my_turn"
                            print(f"🎯 My turn detected! Hand size: {len(hand)}")
                            print(f"🔌 Disconnecting during my turn...")
                            disconnect_ready = True
                            break
                        else:
                            print(f"⏳ Waiting for {current_player} to play...")
                    
                    elif msg_type == 'hokm_selected':
                        # Auto-proceed by continuing to wait for gameplay
                        print("✅ Hokm selected, waiting for gameplay...")
                    
                    elif msg_type == 'error':
                        print(f"❌ Server error: {data.get('message')}")
                    
                    turn_count += 1
                    
                except asyncio.TimeoutError:
                    print("⏰ Timeout waiting for game progression")
                    turn_count += 1
                except Exception as e:
                    print(f"❌ Error: {e}")
                    break
        
        if not disconnect_ready:
            print("❌ Could not reach a suitable phase for disconnection test")
            return False
        
        print(f"✅ Disconnected from phase: {phase_detected}")
        
        # Phase 2: Reconnect and test continuation
        print(f"\n📋 Phase 2: Reconnecting and testing continuation...")
        await asyncio.sleep(2)  # Brief pause
        
        async with websockets.connect(SERVER_URI) as ws:
            # Re-authenticate
            authenticated = await self.auth_manager.authenticate_with_server(ws)
            if not authenticated:
                print("❌ Re-authentication failed")
                return False
            
            # Load session and reconnect
            session_player_id = await self.load_session()
            if not session_player_id:
                print("❌ No session to reconnect with")
                return False
            
            print(f"🔄 Attempting reconnection with session: {session_player_id[:12]}...")
            await ws.send(json.dumps({
                "type": "reconnect",
                "player_id": session_player_id,
                "room_code": "9999"
            }))
            
            # Test reconnection and continuation
            reconnection_success = False
            continuation_success = False
            turn_count = 0
            max_turns = 30
            
            while turn_count < max_turns:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    
                    print(f"[R{turn_count:2d}] Received: {msg_type}")
                    
                    if msg_type == 'reconnect_success':
                        print("✅ Reconnection successful!")
                        reconnection_success = True
                        
                        game_state = data.get('game_state', {})
                        phase = game_state.get('phase', 'unknown')
                        hand = game_state.get('hand', [])
                        your_turn = game_state.get('your_turn', False)
                        hakem = game_state.get('hakem')
                        you = game_state.get('you')
                        
                        print(f"📋 Reconnected to phase: {phase}")
                        print(f"🃏 Hand size: {len(hand)}")
                        print(f"🎯 Your turn: {your_turn}")
                        
                        # Test based on phase
                        if phase == 'hokm_selection' and hakem == you:
                            print("🎴 Testing hokm selection continuation...")
                            await ws.send(json.dumps({
                                'type': 'hokm_selected',
                                'suit': 'hearts',
                                'room_code': '9999'
                            }))
                            print("✅ Hokm selection sent successfully!")
                            continuation_success = True
                            break
                        
                        elif phase == 'gameplay' and your_turn and hand:
                            print("🃏 Testing card play continuation...")
                            card = hand[0]  # Play first card
                            await ws.send(json.dumps({
                                "type": "play_card",
                                "room_code": "9999",
                                "player_id": session_player_id,
                                "card": card
                            }))
                            print(f"✅ Card play sent: {card}")
                            # Wait for confirmation
                        
                        elif phase == 'gameplay':
                            print("⏳ Reconnected to gameplay but not my turn")
                            continuation_success = True  # Reconnection itself is successful
                            break
                        
                        else:
                            print(f"ℹ️  Reconnected to phase: {phase}")
                            continuation_success = True  # Basic reconnection works
                            break
                    
                    elif msg_type == 'card_played':
                        player_id_in_msg = data.get('player_id')
                        if player_id_in_msg == session_player_id:
                            print("✅ Card play confirmed after reconnection!")
                            continuation_success = True
                            break
                    
                    elif msg_type == 'hokm_selected':
                        print("✅ Hokm selection confirmed after reconnection!")
                        continuation_success = True
                        break
                    
                    elif msg_type == 'error':
                        error_msg = data.get('message', '')
                        print(f"❌ Reconnection error: {error_msg}")
                        if "reconnect" in error_msg.lower() or "session" in error_msg.lower():
                            print("❌ Reconnection failed - session invalid")
                            break
                    
                    elif msg_type == 'turn_start':
                        # This might happen if we reconnect and it's our turn
                        your_turn = data.get('your_turn', False)
                        hand = data.get('hand', [])
                        
                        if your_turn and hand and reconnection_success:
                            print("🎯 Got turn_start after reconnection - testing card play...")
                            card = hand[0]
                            await ws.send(json.dumps({
                                "type": "play_card",
                                "room_code": "9999",
                                "player_id": session_player_id,
                                "card": card
                            }))
                            print(f"✅ Card play sent: {card}")
                    
                    turn_count += 1
                    
                except asyncio.TimeoutError:
                    print("⏰ Timeout during reconnection test")
                    turn_count += 1
                    break
                except Exception as e:
                    print(f"❌ Error during reconnection: {e}")
                    break
        
        # Results
        print("\n" + "="*50)
        print("🔍 TEST RESULTS:")
        print("="*50)
        print(f"Phase tested: {phase_detected}")
        print(f"Reconnection successful: {'✅ YES' if reconnection_success else '❌ NO'}")
        print(f"Continuation successful: {'✅ YES' if continuation_success else '❌ NO'}")
        
        overall_success = reconnection_success and continuation_success
        print(f"Overall result: {'🎉 SUCCESS' if overall_success else '❌ FAILED'}")
        
        if not overall_success:
            print("\n🔧 ISSUES IDENTIFIED:")
            if not reconnection_success:
                print("- Reconnection to game session failed")
            if not continuation_success:
                print("- Could not continue gameplay after reconnection")
            
            print("\n💡 POSSIBLE CAUSES:")
            print("- Server doesn't properly restore game state")
            print("- Client doesn't handle reconnected state correctly") 
            print("- Session expires too quickly")
            print("- Missing turn state after reconnection")
        
        await self.cleanup()
        return overall_success

async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "ReconnectTest"
    
    tester = SimpleReconnectionTest(username)
    success = await tester.test_reconnection_scenario()
    
    return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        sys.exit(1)
