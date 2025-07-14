#!/usr/bin/env python3
"""
Debug Client for Reconnection Testing

This is a simplified version of the client specifically designed to test
and debug reconnection issues. It includes extensive logging and simplified
game logic to help identify where reconnection fails.
"""

import asyncio
import websockets
import json
import sys
import os
import time
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

class DebugClient:
    def __init__(self, username="DebugClient"):
        self.username = username
        self.player_id = None
        self.session_file = f".debug_session_{username}_{int(time.time())}"
        self.auth_manager = ClientAuthManager()
        self.game_state = {}
        self.debug_log = []
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {level}: {message}"
        self.debug_log.append(log_entry)
        print(log_entry)
    
    async def save_session(self):
        if self.player_id:
            with open(self.session_file, 'w') as f:
                f.write(self.player_id)
            self.log(f"Session saved: {self.player_id[:12]}...")
    
    async def load_session(self):
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'r') as f:
                    session_id = f.read().strip()
                self.log(f"Session loaded: {session_id[:12]}...")
                return session_id
        except Exception as e:
            self.log(f"Failed to load session: {e}", "ERROR")
        return None
    
    async def cleanup(self):
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
                self.log("Session file cleaned up")
        except:
            pass
    
    async def connect_and_auth(self):
        """Connect and authenticate"""
        ws = await websockets.connect(SERVER_URI)
        self.log("Connected to server")
        
        authenticated = await self.auth_manager.authenticate_with_server(ws)
        if authenticated:
            player_info = self.auth_manager.get_player_info()
            self.player_id = player_info['player_id']
            self.log(f"Authenticated as {player_info['username']}")
            return ws
        else:
            self.log("Authentication failed", "ERROR")
            await ws.close()
            return None
    
    async def join_or_reconnect(self, ws):
        """Join game or reconnect if session exists"""
        session_id = await self.load_session()
        
        if session_id and session_id == self.player_id:
            self.log("Attempting reconnection...")
            await ws.send(json.dumps({
                "type": "reconnect",
                "player_id": session_id,
                "room_code": "9999"
            }))
            return "reconnect"
        else:
            self.log("Joining as new player...")
            await ws.send(json.dumps({
                "type": "join",
                "room_code": "9999"
            }))
            return "join"
    
    async def handle_message(self, ws, msg):
        """Handle incoming message with detailed logging"""
        try:
            data = json.loads(msg)
        except json.JSONDecodeError as e:
            self.log(f"JSON decode error: {e}", "ERROR")
            return False
        
        msg_type = data.get('type')
        self.log(f"Received: {msg_type}")
        
        # Update game state
        self.game_state['last_message'] = msg_type
        self.game_state['last_data'] = data
        
        if msg_type == 'join_success':
            self.player_id = data.get('player_id', self.player_id)
            await self.save_session()
            self.log("Join successful")
            
        elif msg_type == 'reconnect_success':
            self.log("✅ Reconnection successful!")
            game_state_data = data.get('game_state', {})
            self.game_state.update(game_state_data)
            
            phase = game_state_data.get('phase', 'unknown')
            hand = game_state_data.get('hand', [])
            your_turn = game_state_data.get('your_turn', False)
            hakem = game_state_data.get('hakem')
            you = game_state_data.get('you')
            hokm = game_state_data.get('hokm')
            
            self.log(f"Reconnected to phase: {phase}")
            self.log(f"Hand size: {len(hand)}")
            self.log(f"Your turn: {your_turn}")
            self.log(f"Hakem: {hakem}")
            self.log(f"You: {you}")
            self.log(f"Hokm: {hokm}")
            
            # Test immediate actions
            if phase == 'hokm_selection' and hakem == you:
                self.log("🎴 Testing hokm selection after reconnection...")
                await ws.send(json.dumps({
                    'type': 'hokm_selected',
                    'suit': 'hearts',
                    'room_code': '9999'
                }))
                self.log("Hokm selection command sent")
                
            elif phase == 'gameplay' and your_turn and hand:
                self.log("🃏 Testing card play after reconnection...")
                card = hand[0]
                await ws.send(json.dumps({
                    "type": "play_card",
                    "room_code": "9999",
                    "player_id": self.player_id,
                    "card": card
                }))
                self.log(f"Card play command sent: {card}")
            
        elif msg_type == 'initial_deal':
            is_hakem = data.get('is_hakem', False)
            hand = data.get('hand', [])
            self.log(f"Initial deal - Hakem: {is_hakem}, Hand: {len(hand)} cards")
            
            if is_hakem:
                self.log("🎴 I am hakem - will disconnect and test reconnection...")
                return "disconnect_hokm"
                
        elif msg_type == 'turn_start':
            your_turn = data.get('your_turn', False)
            hand = data.get('hand', [])
            current_player = data.get('current_player')
            
            self.log(f"Turn start - Current: {current_player}, Your turn: {your_turn}, Hand: {len(hand)}")
            
            if your_turn and hand:
                self.log("🎯 My turn detected - will disconnect and test reconnection...")
                return "disconnect_turn"
                
        elif msg_type == 'card_played':
            player_id_in_msg = data.get('player_id')
            card = data.get('card')
            if player_id_in_msg == self.player_id:
                self.log(f"✅ My card played successfully: {card}")
            else:
                self.log(f"Other player played: {card}")
                
        elif msg_type == 'hokm_selected':
            suit = data.get('suit')
            self.log(f"✅ Hokm selected successfully: {suit}")
            
        elif msg_type == 'error':
            error_msg = data.get('message', '')
            self.log(f"❌ Server error: {error_msg}", "ERROR")
            
        else:
            self.log(f"Other message: {msg_type}")
        
        return True
    
    async def run_reconnection_test(self):
        """Run the main reconnection test"""
        self.log("🔧 Starting Debug Reconnection Test")
        self.log(f"Username: {self.username}")
        
        # Phase 1: Connect and get to a disconnection point
        self.log("\n📋 Phase 1: Initial connection and game progression...")
        
        ws = await self.connect_and_auth()
        if not ws:
            return False
        
        join_type = await self.join_or_reconnect(ws)
        
        # Wait for a good disconnection point
        disconnect_reason = None
        turn_count = 0
        max_turns = 60
        
        try:
            while turn_count < max_turns and not disconnect_reason:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                result = await self.handle_message(ws, msg)
                
                if isinstance(result, str) and result.startswith("disconnect_"):
                    disconnect_reason = result
                    break
                
                turn_count += 1
                
        except asyncio.TimeoutError:
            self.log("Timeout waiting for disconnection point", "WARNING")
        except Exception as e:
            self.log(f"Error in phase 1: {e}", "ERROR")
        finally:
            await ws.close()
            self.log("Disconnected from phase 1")
        
        if not disconnect_reason:
            self.log("❌ Could not reach suitable disconnection point", "ERROR")
            await self.cleanup()
            return False
        
        self.log(f"✅ Disconnected at: {disconnect_reason}")
        
        # Phase 2: Reconnect and test continuation
        self.log(f"\n📋 Phase 2: Reconnection test...")
        await asyncio.sleep(2)
        
        ws = await self.connect_and_auth()
        if not ws:
            return False
        
        join_type = await self.join_or_reconnect(ws)
        
        # Test reconnection
        reconnection_success = False
        continuation_success = False
        turn_count = 0
        max_turns = 30
        
        try:
            while turn_count < max_turns:
                msg = await asyncio.wait_for(ws.recv(), timeout=15.0)
                result = await self.handle_message(ws, msg)
                
                data = json.loads(msg)
                msg_type = data.get('type')
                
                if msg_type == 'reconnect_success':
                    reconnection_success = True
                elif msg_type in ['card_played', 'hokm_selected']:
                    if data.get('player_id') == self.player_id:
                        continuation_success = True
                        break
                elif msg_type == 'error' and "reconnect" in data.get('message', '').lower():
                    break
                
                turn_count += 1
                
        except asyncio.TimeoutError:
            self.log("Timeout during reconnection test", "WARNING")
        except Exception as e:
            self.log(f"Error in phase 2: {e}", "ERROR")
        finally:
            await ws.close()
            self.log("Disconnected from phase 2")
        
        # Results
        self.log("\n" + "="*50)
        self.log("🔍 TEST RESULTS:")
        self.log("="*50)
        self.log(f"Disconnect reason: {disconnect_reason}")
        self.log(f"Reconnection successful: {'✅' if reconnection_success else '❌'}")
        self.log(f"Continuation successful: {'✅' if continuation_success else '❌'}")
        
        overall_success = reconnection_success and continuation_success
        self.log(f"Overall result: {'🎉 SUCCESS' if overall_success else '❌ FAILED'}")
        
        if not overall_success:
            self.log("\n🔧 DEBUGGING INFO:")
            self.log(f"Last game state: {self.game_state}")
            self.log("\nLast 10 log entries:")
            for entry in self.debug_log[-10:]:
                self.log(entry)
        
        # Save debug log
        log_file = f"debug_reconnection_{int(time.time())}.log"
        try:
            with open(log_file, 'w') as f:
                f.write('\n'.join(self.debug_log))
            self.log(f"Debug log saved to {log_file}")
        except Exception as e:
            self.log(f"Failed to save debug log: {e}", "ERROR")
        
        await self.cleanup()
        return overall_success

async def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "DebugClient"
    
    client = DebugClient(username)
    success = await client.run_reconnection_test()
    
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
